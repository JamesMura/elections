# -*- coding: utf-8 -*-
from datetime import datetime
from itertools import ifilter
from mongoengine import signals
from wtforms import (
    Form,
    IntegerField, SelectField, SelectMultipleField, StringField,
    validators, widgets
)
from flask import g
from .. import services, models
from ..participants.utils import update_participant_completion_rating
import json
import re


ugly_phone = re.compile('[^\d]*')


def update_submission_version(sender, document, **kwargs):
    if sender != services.submissions.__model__:
        return

    # save actual version data
    data_fields = document.form.tags
    if document.form.form_type == 'INCIDENT':
        data_fields.extend(['status', 'witness'])
    version_data = {k: document[k] for k in data_fields if k in document}

    channel = 'SMS'

    services.submission_versions.create(
        submission=document,
        data=json.dumps(version_data),
        timestamp=datetime.utcnow(),
        channel=channel,
        identity=g.get('phone', '')
    )


class BaseQuestionnaireForm(Form):
    form = StringField(
        u'Form', validators=[validators.required()],
        filters=[lambda data: services.forms.get(pk=data)])
    participant = StringField(
        u'Participant', validators=[validators.required()],
        filters=[lambda data: services.participants.get(participant_id=data)])
    sender = StringField(u'Sender', validators=[validators.required()])
    comment = StringField(u'Comment', validators=[validators.optional()])

    def process(self, formdata=None, obj=None, **kwargs):
        self._formdata = formdata
        return super(BaseQuestionnaireForm, self).process(
            formdata, obj, **kwargs)

    def validate(self, *args, **kwargs):
        success = super(BaseQuestionnaireForm, self).validate(*args, **kwargs)
        if success and self._formdata:
            unknown_fields = filter(
                lambda f: f not in self._fields.keys(),
                self._formdata.keys())
            if unknown_fields:
                if type(self._errors) == dict:
                    self._errors.update({'__all__': unknown_fields})
                else:
                    self._errors = {'__all__': unknown_fields}

                success = False

        return success

    def save(self):
        ignored_fields = ['form', 'participant', 'sender', 'comment']
        submission = None

        # also ignore fields that have errors so as not to save them
        ignored_fields.extend(self.errors.keys())
        try:
            if self.data.get('form').form_type == 'CHECKLIST':
                submission = services.submissions.get(
                    contributor=self.data.get('participant'),
                    form=self.data.get('form'), submission_type='O')
                if self.data.get('comment'):
                    services.submission_comments.create_comment(
                        submission, self.data.get('comment'))
            else:
                submission = models.Submission(
                    form=self.data.get('form'),
                    contributor=self.data.get('participant'),
                    location=self.data.get('participant').location,
                    created=datetime.utcnow(), deployment=g.event.deployment,
                    event=g.event)
                if self.data.get('comment'):
                    submission.description = self.data.get('comment')

            if submission:
                form_fields = filter(lambda f: f not in ignored_fields,
                                     self.data.keys())
                change_detected = False
                for form_field in form_fields:
                    if isinstance(self.data.get(form_field), int):
                        change_detected = True
                        if (
                            getattr(submission, form_field, None) !=
                            self.data.get(form_field)
                        ):
                            setattr(
                                submission, form_field,
                                self.data.get(form_field))

                if change_detected:
                    g.phone = self.data.get('sender')

                    # confirm if phone number is known and verified
                    participant = self.data.get('participant')

                    # retrieve the first phone contact that matches
                    phone_contact = next(ifilter(
                        lambda phone: ugly_phone.sub('', g.phone) ==
                        phone.number,
                        participant.phones), False)
                    if phone_contact:
                        submission.sender_verified = phone_contact.verified
                        phone_contact.last_seen = datetime.utcnow()
                        participant.save()
                    else:
                        submission.sender_verified = False
                        phone_contact = models.PhoneContact(
                            number=g.phone,
                            verified=False, last_seen=datetime.utcnow())
                        participant.update(add_to_set__phones=phone_contact)

                    with signals.post_save.connected_to(
                        update_submission_version,
                        sender=services.submissions.__model__
                    ):
                        submission.save()

                    # update completion rating for participant
                    if submission.form.form_type == 'CHECKLIST':
                        update_participant_completion_rating(participant)
        except models.Submission.DoesNotExist:
            pass

        return submission


def build_questionnaire(form, data=None):
    fields = {'groups': []}

    for group in form.groups:
        groupspec = (group.name, [])

        for field in group.fields:
            # if the field has options, create a list of choices
            if field.options:
                choices = [(v, k) for k, v in field.options.iteritems()]

                if field.allows_multiple_values:
                    fields[field.name] = SelectMultipleField(
                        field.name,
                        choices=choices,
                        coerce=int,
                        description=field.description,
                        option_widget=widgets.CheckboxInput(),
                        validators=[validators.optional()],
                        widget=widgets.ListWidget(prefix_label=False)
                    )
                else:
                    fields[field.name] = SelectField(
                        field.name,
                        choices=choices,
                        coerce=int,
                        description=field.description,
                        validators=[validators.optional()],
                        widget=widgets.TextInput()
                    )
            else:
                if form.form_type == 'CHECKLIST':
                    fields[field.name] = IntegerField(
                        field.name,
                        description=field.description,
                        validators=[
                            validators.optional(),
                            validators.NumberRange(min=field.min_value,
                                                   max=field.max_value)]
                    )
                else:
                    fields[field.name] = IntegerField(
                        field.name,
                        description=field.description,
                        validators=[validators.optional()]
                    )

        fields['groups'].append(groupspec)

    form_class = type('QuestionnaireForm', (BaseQuestionnaireForm,), fields)

    return form_class(data)

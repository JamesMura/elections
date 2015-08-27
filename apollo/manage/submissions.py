from flask.ext.script import Command, prompt_choices
from .. import services, models


class InitializeSubmissionsCommand(Command):
    """Initializes submissions in readiness to accept data"""

    def run(self):
        deployments = models.Deployment.objects()
        option = prompt_choices('Deployment', [
            (str(i), v) for i, v in enumerate(deployments, 1)])
        deployment = deployments[int(option) - 1]
        events = services.events.find(deployment=deployment)
        option = prompt_choices('Event', [
            (str(i), v) for i, v in enumerate(events, 1)])
        event = events[int(option) - 1]
        roles = services.participant_roles.find(deployment=deployment)
        option = prompt_choices('Role', [
            (str(i), v) for i, v in enumerate(roles, 1)])
        role = roles[int(option) - 1]
        forms = services.forms.find(
            deployment=deployment, events=event, form_type='CHECKLIST')
        option = prompt_choices('Role', [
            (str(i), v) for i, v in enumerate(forms, 1)])
        form = forms[int(option) - 1]

        for o in services.participants.find(
            role=role, deployment=deployment, event=event
        ):
            submission, _ = models.Submission.objects.get_or_create(
                form=form, contributor=o, location=o.location,
                created=event.start_date, deployment=event.deployment,
                event=event, submission_type='O')
            # hack to force creation of a master submission
            submission.master

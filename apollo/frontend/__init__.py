from functools import wraps


from flask import g, render_template, session, request, redirect, url_for
from flask.ext.admin import AdminIndexView
from flask.ext.login import user_logged_out
from flask.ext.principal import identity_loaded
from flask.ext.security import MongoEngineUserDatastore, current_user

from .. import factory, models, services
from ..core import admin, db, menu, security, gravatar
from ..security_ext_forms import DeploymentLoginForm

from . import assets, permissions
from .helpers import set_request_presets, CustomMongoEngineSessionInterface
from . import template_filters


custom_filters = {
    'checklist_question_summary': template_filters.checklist_question_summary,
    'get_location_for_type': template_filters.get_location_for_type,
    'pagelist': template_filters.gen_page_list,
    'percent_of': template_filters.percent_of,
    'timestamp': template_filters.mkunixtimestamp,
    'mean_filter': template_filters.mean_filter,
    'total_registered': template_filters.total_registered,
    'all_votes_total': template_filters.all_votes_total,
    'all_votes_total_pct': template_filters.all_votes_total_pct,
    'all_votes_total_moe': template_filters.all_votes_total_margin_of_error,
    'valid_votes_total': template_filters.valid_votes_total,
    'vote_count': template_filters.vote_count,
    'rejected_count': template_filters.rejected_count,
    'vote_proportion': template_filters.vote_proportion,
    'rejected_proportion': template_filters.rejected_proportion,
    'vote_moe': template_filters.vote_margin_of_error,
    'rejected_moe': template_filters.rejected_margin_of_error,
    'reported': template_filters.reported,
    'missing': template_filters.missing,
    'reported_pct': template_filters.reported_pct,
    'missing_pct': template_filters.missing_pct
}


def init_admin(admin, app):
    class AdminIndex(AdminIndexView):
        def is_accessible(self):
            try:
                role = models.Role.objects.get(name='admin')
            except models.Role.DoesNotExist:
                return False
            return (
                current_user.is_authenticated() and current_user.has_role(role)
            )

    admin.init_app(app)
    admin.index_view = AdminIndex()


def create_app(settings_override=None, register_security_blueprint=True):
    """Returns the frontend application instance"""
    app = factory.create_app(__name__, __path__, settings_override)

    # Init assets
    assets.init_app(app)

    menu.init_app(app)
    gravatar.init_app(app)

    userdatastore = MongoEngineUserDatastore(db, models.User, models.Role)

    security.init_app(app, userdatastore,
                      login_form=DeploymentLoginForm,
                      register_blueprint=register_security_blueprint)
    app.session_interface = CustomMongoEngineSessionInterface(db)

    init_admin(admin, app)

    # Register custom error handlers
    if not app.debug:
        for e in [500, 404, 403]:
            app.errorhandler(e)(handle_error)

    @app.before_first_request
    def create_user_roles():
        userdatastore.find_or_create_role('clerk')
        userdatastore.find_or_create_role('manager')
        userdatastore.find_or_create_role('analyst')
        userdatastore.find_or_create_role('admin')

        # permissions
        services.perms.get_or_create(action='view_events')
        services.perms.get_or_create(action='view_messages')
        services.perms.get_or_create(action='view_analyses')

        services.perms.get_or_create(action='add_submission')

        services.perms.get_or_create(action='edit_forms')
        services.perms.get_or_create(action='edit_locations')
        services.perms.get_or_create(action='edit_participant')
        services.perms.get_or_create(action='edit_submission')
        services.perms.get_or_create(action='edit_location')

        services.perms.get_or_create(action='import_participants')
        services.perms.get_or_create(action='import_locations')

        services.perms.get_or_create(action='export_participants')
        services.perms.get_or_create(action='export_messages')
        services.perms.get_or_create(action='export_submissions')
        services.perms.get_or_create(action='export_locations')

        services.perms.get_or_create(action='send_messages')

    # register deployment selection middleware
    app.before_request(set_request_presets)

    # add Jinja2 filters
    app.jinja_env.filters.update(custom_filters)

    # Login and logout signal handlers
    # user_logged_out.connect(lambda app, user: session.clear())
    user_logged_out.connect(clear_session)

    @identity_loaded.connect_via(app)
    def on_identity_loaded(sender, identity):
        needs = services.perms.get_all_needs(
            models.User(**identity.user._data))

        for need in needs:
            identity.provides.add(need)

    @app.context_processor
    def inject_permissions():
        ga_key = app.config.get('GOOGLE_ANALYTICS_KEY')
        return dict(perms=permissions, ga_key=ga_key)

    # clickjacking protection
    @app.after_request
    def frame_buster(response):
        response.headers['X-Frame-Options'] = app.config.get(
            'X_FRAME_OPTIONS', 'DENY')
        return response

    return app


def clear_session(app, user):
    # clear session
    session.clear()

    # pop request globals
    delattr(g, 'deployment')
    delattr(g, 'event')
    delattr(g, 'locale')


def handle_error(e):
    code = getattr(e, 'code', 500)
    if code == 403:
        session['redirected_from'] = request.url
        return redirect(url_for('security.login'))
    else:
        return render_template('{code}.html'.format(code=code)), code


def route(bp, *args, **kwargs):
    def decorator(f):
        @bp.route(*args, **kwargs)
        @wraps(f)
        def wrapper(*args, **kwargs):
            return f(*args, **kwargs)
        return f

    return decorator

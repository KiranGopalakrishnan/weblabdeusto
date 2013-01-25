import os
import sha
import random
import traceback
import SocketServer

from wtforms.fields import PasswordField
from wtforms.validators import Email

from flask import Flask, Markup, request, redirect, abort

import flask_admin.contrib.sqlamodel.filters as filters

from flask.ext.admin import expose, AdminIndexView, Admin, BaseView
from flask.ext.admin.contrib.sqlamodel import ModelView, tools
from flask.ext.admin.model.form import InlineFormAdmin


from sqlalchemy.orm import scoped_session, sessionmaker

import wsgiref.simple_server

if __name__ == '__main__':
    import sys
    sys.path.insert(0, '.')

from voodoo.sessions.session_id import SessionId
from weblab.core.exc import SessionNotFoundError

import weblab.db.model as model
from weblab.db.gateway import AbstractDatabaseGateway
import weblab.comm.server as abstract_server

class FilterAnyEqual(filters.FilterEqual):
    def __init__(self, column, name, column_any, **kwargs):
        self.column_any = column_any
        super(FilterAnyEqual, self).__init__(column, name, **kwargs)

    def apply(self, query, value):
        return query.filter(self.column_any.any(self.column == value))

class FilterAnyNotEqual(filters.FilterNotEqual):
    def __init__(self, column, name, column_any, **kwargs):
        self.column_any = column_any
        super(FilterAnyNotEqual, self).__init__(column, name, **kwargs)

    def apply(self, query, value):
        return query.filter(self.column_any.any(self.column != value))

class FilterAnyLike(filters.FilterLike):
    def __init__(self, column, name, column_any, **kwargs):
        self.column_any = column_any
        super(FilterAnyLike, self).__init__(column, name, **kwargs)

    def apply(self, query, value):
        stmt = tools.parse_like_term(value)
        return query.filter(self.column_any.any(self.column.ilike(stmt)))

class FilterAnyNotLike(filters.FilterNotLike):
    def __init__(self, column, name, column_any, **kwargs):
        self.column_any = column_any
        super(FilterAnyNotLike, self).__init__(column, name, **kwargs)

    def apply(self, query, value):
        stmt = tools.parse_like_term(value)
        return query.filter(self.column_any.any(~self.column.ilike(stmt)))

def generate_filter_any(column, name, column_any, iter_type = tuple):
    return iter_type( 
                    (FilterAnyEqual(column, name, column_any), FilterAnyNotEqual(column, name, column_any), 
                     FilterAnyLike(column, name, column_any), FilterAnyNotLike(column, name, column_any)) )


def get_filter_number(view, name):
    return [ n  
                for (n, f) in enumerate(view._filters) 
                if unicode(f.column).endswith(name) 
                    and isinstance(f.operation.im_self, filters.FilterEqual) 
        ][0]

class AdministratorView(BaseView):

    def is_accessible(self):
        return AdministrationApplication.INSTANCE.is_admin()

    def _handle_view(self, name, **kwargs):
        if not self.is_accessible():
            return redirect(request.url.split('/weblab/administration')[0] + '/weblab/client')

        return super(AdministratorView, self)._handle_view(name, **kwargs)


class AdministratorModelView(ModelView):

    def is_accessible(self):
        return AdministrationApplication.INSTANCE.is_admin()

    def _handle_view(self, name, **kwargs):
        if not self.is_accessible():
            return redirect(request.url.split('/weblab/administration')[0] + '/weblab/client')

        return super(AdministratorModelView, self)._handle_view(name, **kwargs)


    # 
    # TODO XXX FIXME: This may be a bug. However, whenever this is commented,
    # Flask-Admin does this:
    #
    #       # Auto join
    #       for j in self._auto_joins:
    #                   query = query.options(subqueryload(j))
    # 
    # And some (weird) results in UserUsedExperiment are not shown, while other yes
    # 

    def scaffold_auto_joins(self):
        return []

SAME_DATA = object()

def show_link(klass, filter_name, field, name, view = 'View'):

    instance      = klass.INSTANCE
    url           = instance.url

    link = u'<a href="%s?' % url

    if isinstance(filter_name, basestring):
        filter_numbers = [ getattr(instance, u'%s_filter_number' % filter_name) ]
    else:
        filter_numbers = [ getattr(instance, u'%s_filter_number' % fname) for fname in filter_name]

    if isinstance(name, basestring):
        names = [name]
    else:
        names = name

    for pos, (filter_number, name) in enumerate(zip(filter_numbers, names)):
        if '.' not in name:
            data = getattr(field, name)
        else:
            variables = name.split('.')
            current = field
            data = None
            for variable in variables:
                current = getattr(current, variable)
                if current is None:
                    data = ''
                    break
            if data is None:
                data = current
        link += u'flt%s_%s=%s&' % (pos + 1, filter_number, data)

    if view == SAME_DATA:
        view = data

    link = link[:-1] + u'">%s</a>' % view

    return Markup(link)
   
class UserAuthForm(InlineFormAdmin):
    def postprocess_form(self, form_class):
        form_class.configuration = PasswordField('configuration', description = 'Detail the password (DB), Facebook ID -the number- (Facebook), OpenID identifier.')
        return form_class

class UsersPanel(AdministratorModelView):

    column_list = ('role', 'login', 'full_name', 'email', 'groups', 'logs')
    column_searchable_list = ('full_name', 'login')
    column_filters = ( 'full_name', 'login','role', 'email'
                    ) + generate_filter_any(model.DbGroup.name.property.columns[0], 'Group', model.DbUser.groups)


    form_excluded_columns = 'avatar',
    form_args = dict(email = dict(validators = [Email()]) )

    column_descriptions = dict( login     = 'Username (all letters, dots and numbers)', 
                                full_name ='First and Last name',
                                email     = 'Valid e-mail address',
                                avatar    = 'Not implemented yet, it should be a public URL for a user picture.' )

    inline_models = (UserAuthForm(model.DbUserAuth),)

    column_formatters = dict(
                            role   = lambda c, u, p: show_link(UsersPanel,              'role', u, 'role.name', SAME_DATA),
                            groups = lambda c, u, p: show_link(GroupsPanel,             'user', u, 'login'),
                            logs   = lambda c, u, p: show_link(UserUsedExperimentPanel, 'user', u, 'login'),
                        )

    INSTANCE = None

    def __init__(self, session, **kwargs):
        super(UsersPanel, self).__init__(model.DbUser, session, **kwargs)
        self.login_filter_number = get_filter_number(self, u'User.login')
        self.group_filter_number = get_filter_number(self, u'Group.name')
        self.role_filter_number  = get_filter_number(self, u'Role.name')
        UsersPanel.INSTANCE = self

    def on_model_change(self, form, user_model):
        auths = {}
        for auth_instance in user_model.auths:
            if auth_instance.auth in auths:
                raise Exception("You can not have two equal auth types (of type %s)" % auth_instance.auth.name)
            else:
                auths[auth_instance.auth] = auth_instance
                if auth_instance.auth.auth_type.name.lower() == 'db':
                    password = auth_instance.configuration
                    if len(password) < 6:
                        raise Exception("Password too short")
                    auth_instance.configuration = self._password2sha(password)
                elif auth_instance.auth.auth_type.name.lower() == 'facebook':
                    try:
                        int(auth_instance.configuration)
                    except:
                        raise Exception("Use a numeric ID for Facebook")
                # Other validations would be here


    def _password2sha(self, password):
        randomstuff = ""
        for _ in range(4):
            c = chr(ord('a') + random.randint(0,25))
            randomstuff += c
        password = password if password is not None else ''
        return randomstuff + "{sha}" + sha.new(randomstuff + password).hexdigest()

class GroupsPanel(AdministratorModelView):

    column_searchable_list = ('name',)
    column_list = ('name','parent', 'users')

    column_filters = ( ('name',) 
                        + generate_filter_any(model.DbUser.login.property.columns[0], 'User login', model.DbGroup.users)
                        + generate_filter_any(model.DbUser.full_name.property.columns[0], 'User name', model.DbGroup.users)
                    )

    column_formatters = dict(
                            users = lambda c, g, p: show_link(UsersPanel, 'group', g, 'name'),
                        )

    INSTANCE = None

    def __init__(self, session, **kwargs):
        super(GroupsPanel, self).__init__(model.DbGroup, session, **kwargs)

        self.user_filter_number  = get_filter_number(self, u'User.login')

        GroupsPanel.INSTANCE = self

class DetailsView(AdministratorView):

    INSTANCE = None

    def __init__(self, db_session, **kwargs):
        super(DetailsView, self).__init__(**kwargs)
        self._db_session = db_session

        DetailsView.INSTANCE = self

    @expose()
    def index(self):
        # TODO: render
        return "This page shows the details of each entry. Go to Logs, User and click on Details to see a detail."

    @expose('/<int:id>')
    def detail(self, id):
        uue = self._db_session.query(model.DbUserUsedExperiment).filter_by(id = id).first()
        if uue is None:
            return abort(404)

        # TODO: render
        return "Gotcha: %s" % uue.start_date

class UserUsedExperimentPanel(AdministratorModelView):

    column_auto_select_related = True
    column_select_related_list = ('user',)
    can_delete = False
    can_edit   = False
    can_create = False

    # column_searchable_list = ('user', 'experiment', 'origin')
    column_list    = ( 'user', 'experiment', 'start_date', 'end_date', 'origin', 'coord_address','details')
    column_filters = ( 'user', 'start_date', 'end_date', 'experiment', 'origin', 'coord_address')

    column_formatters = dict(
                    user       = lambda c, uue, p: show_link(UsersPanel, 'login', uue, 'user.login', SAME_DATA),
                    experiment = lambda c, uue, p: show_link(ExperimentPanel, ('name', 'category'), uue, ('experiment.name', 'experiment.category.name'), uue.experiment ),
                    details    = lambda c, uue, p: Markup('<a href="%s/%s">Details</a>' % (DetailsView.INSTANCE.url, uue.id)),
                )

    action_disallowed_list = ['create','edit','delete']

    INSTANCE = None

    def __init__(self, session, **kwargs):
        super(UserUsedExperimentPanel, self).__init__(model.DbUserUsedExperiment, session, **kwargs)

        self.user_filter_number  = get_filter_number(self, u'User.login')
        self.experiment_filter_number  = get_filter_number(self, u'Experiment.name')
        # self.experiment_category_filter_number  = get_filter_number(self, u'Category.name')

        UserUsedExperimentPanel.INSTANCE = self

class ExperimentCategoryPanel(AdministratorModelView):
   
    column_searchable_list = ('name',)
    column_list    = ('name', 'experiments')
    column_filters = ( 'name', ) 

    column_formatters = dict(
                    experiments = lambda co, c, p: show_link(ExperimentPanel, 'category', c, 'name')
                )

    INSTANCE = None

    def __init__(self, session, **kwargs):
        super(ExperimentCategoryPanel, self).__init__(model.DbExperimentCategory, session, **kwargs)
        
        self.category_filter_number  = get_filter_number(self, u'Category.name')

        ExperimentCategoryPanel.INSTANCE = self

class ExperimentPanel(AdministratorModelView):
    
    # column_searchable_list = ('name','category')
    column_list = ('category', 'name', 'start_date', 'end_date', 'uses')

    
    column_filters = ('name','category')

    column_formatters = dict(
                        category = lambda c, e, p: show_link(ExperimentCategoryPanel, 'category', e, 'category.name', SAME_DATA),
                        uses     = lambda c, e, p: show_link(UserUsedExperimentPanel, 'experiment', e, 'name'),
                )

    INSTANCE = None

    def __init__(self, session, **kwargs):
        super(ExperimentPanel, self).__init__(model.DbExperiment, session, **kwargs)
        
        self.name_filter_number  = get_filter_number(self, u'Experiment.name')
        self.category_filter_number  = get_filter_number(self, u'Category.name')
        ExperimentPanel.INSTANCE = self

class PermissionTypePanel(AdministratorModelView):

    column_list = ('name', 'description')
    can_edit   = False
    can_create = False
    can_delete = False
    inline_models = (model.DbPermissionTypeParameter,)

    def __init__(self, session, **kwargs):
        super(PermissionTypePanel, self).__init__(model.DbPermissionType, session, **kwargs)

def display_parameters(context, permission, p):
    parameters = u''
    for parameter in permission.parameters:
        parameters += u'%s = %s, ' % (parameter.permission_type_parameter.name, parameter.value)
    permission_str = u'%s(%s)' % (permission.permission_type.name, parameters[:-2])
    return permission_str

class UserPermissionPanel(AdministratorModelView):

    column_searchable_list = ('permanent_id', 'comments')
    # column_searchable_list = ('user','permission', 'permanent_id', 'comments')
    # column_filters = ( 'user', 'permission', 'permanent_id', 'date', 'comments' )
    column_list = ('user', 'permission', 'permanent_id', 'date', 'comments')
    column_formatters = dict( permission = display_parameters,
    user = lambda c, u, p: unicode(u.user) )

    inline_models = (model.DbUserPermissionParameter,)

    def __init__(self, session, **kwargs):
        super(UserPermissionPanel, self).__init__(model.DbUserPermission, session, **kwargs)

class GroupPermissionPanel(AdministratorModelView):

    # column_searchable_list = ('group','permission', 'permanent_id', 'comments')
    # column_filters = ( 'group', 'permission', 'permanent_id', 'date', 'comments' )
    column_list = ('group', 'permission', 'permanent_id', 'date', 'comments')
    column_formatters = dict( permission = display_parameters )
    inline_models = (model.DbGroupPermissionParameter,)

    def __init__(self, session, **kwargs):
        super(GroupPermissionPanel, self).__init__(model.DbGroupPermission, session, **kwargs)

class RolePermissionPanel(AdministratorModelView):

    # column_searchable_list = ('role','permission', 'permanent_id', 'comments')
    # column_filters = ( 'role', 'permission', 'permanent_id', 'date', 'comments' )
    column_list = ('role', 'permission', 'permanent_id', 'date', 'comments')
    column_formatters = dict( permission = display_parameters )
    inline_models = (model.DbRolePermissionParameter,)

    def __init__(self, session, **kwargs):
        super(RolePermissionPanel, self).__init__(model.DbRolePermission, session, **kwargs)

class HomeView(AdminIndexView):

    @expose()
    def index(self):
        return self.render("admin-index.html")


class AdministrationApplication(AbstractDatabaseGateway):

    INSTANCE = None

    def __init__(self, cfg_manager, ups, bypass_authz = False):

        super(AdministrationApplication, self).__init__(cfg_manager)

        self.ups = ups

        db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=self.engine))

        self.app = Flask(__name__)
        self.app.config['SECRET_KEY'] = os.urandom(32)
        url = '/weblab/administration'
        self.admin = Admin(index_view = HomeView(url = url),name = 'WebLab-Deusto Admin', url = url)

        self.admin.add_view(UsersPanel(db_session,  category = 'General', name = 'Users',  endpoint = 'general/users'))
        self.admin.add_view(GroupsPanel(db_session, category = 'General', name = 'Groups', endpoint = 'general/groups'))

        self.admin.add_view(UserUsedExperimentPanel(db_session, category = 'Logs', name = 'User logs', endpoint = 'logs/users'))
        self.admin.add_view(DetailsView(db_session,             category = 'Logs', name = 'Details', endpoint = 'logs/details'))

        self.admin.add_view(ExperimentCategoryPanel(db_session, category = 'Experiments', name = 'Categories',  endpoint = 'experiments/categories'))
        self.admin.add_view(ExperimentPanel(db_session,         category = 'Experiments', name = 'Experiments', endpoint = 'experiments/experiments'))

        self.admin.add_view(PermissionTypePanel(db_session,  category = 'Permissions', name = 'Types', endpoint = 'permissions/types'))
        self.admin.add_view(UserPermissionPanel(db_session,  category = 'Permissions', name = 'User',  endpoint = 'permissions/user'))
        self.admin.add_view(GroupPermissionPanel(db_session, category = 'Permissions', name = 'Group', endpoint = 'permissions/group'))
        self.admin.add_view(RolePermissionPanel(db_session,  category = 'Permissions', name = 'Roles', endpoint = 'permissions/role'))

        self.admin.init_app(self.app)

        self.bypass_authz = bypass_authz

        AdministrationApplication.INSTANCE = self

    def is_admin(self):
        if self.bypass_authz:
            return True

        try:
            session_id = SessionId((request.cookies.get('weblabsessionid') or '').split('.')[0])
            try:
                permissions = self.ups.get_user_permissions(session_id)
            except SessionNotFoundError:
                # Gotcha
                return False

            admin_permissions = [ permission for permission in permissions if permission.name == 'admin_panel_access' ]
            if len(admin_permissions) == 0:
                return False

            if admin_permissions[0].parameters[0].value:
                return True

            return False
        except:
            traceback.print_exc()
            return False

#####################################################################################
# 
# TODO: All this code below depends on the old and deprecated communication system of 
# WebLab-Deusto, which should be refactored to be less complex.
# 

class WsgiHttpServer(SocketServer.ThreadingMixIn, wsgiref.simple_server.WSGIServer):
    daemon_threads      = True
    request_queue_size  = 50 #TODO: parameter!
    allow_reuse_address = True

    def __init__(self, server_address, handler_class, application):
        wsgiref.simple_server.WSGIServer.__init__(self, server_address, handler_class)
        self.set_app(application)

    def get_request(self):
        sock, addr = wsgiref.simple_server.WSGIServer.get_request(self)
        sock.settimeout(None)
        return sock, addr

class RemoteFacadeServerWSGI(abstract_server.AbstractProtocolRemoteFacadeServer):
    
    protocol_name = "wsgi"

    WSGI_HANDLER = wsgiref.simple_server.WSGIRequestHandler

    def _retrieve_configuration(self):
        values = self.parse_configuration(
                self._rfs.FACADE_WSGI_PORT,
                **{
                    self._rfs.FACADE_WSGI_LISTEN: self._rfs.DEFAULT_FACADE_WSGI_LISTEN
                }
           )
        listen = getattr(values, self._rfs.FACADE_WSGI_LISTEN)
        port   = getattr(values, self._rfs.FACADE_WSGI_PORT)
        return listen, port

    def initialize(self):
        listen, port = self._retrieve_configuration()
        the_server_route = self._configuration_manager.get_value( self._rfs.FACADE_SERVER_ROUTE, self._rfs.DEFAULT_SERVER_ROUTE )
        core_server_url  = self._configuration_manager.get_value( 'core_server_url', '' )
        if core_server_url.startswith('http://') or core_server_url.startswith('https://'):
            without_protocol = '//'.join(core_server_url.split('//')[1:])
            the_location = '/' + ( '/'.join(without_protocol.split('/')[1:]) )
        else:
            the_location = '/'
        timeout = self.get_timeout()

        class NewWsgiHttpHandler(self.WSGI_HANDLER):
            server_route   = the_server_route
            location       = the_location

        self._server = WsgiHttpServer((listen, port), NewWsgiHttpHandler, self._rfm)
        self._server.socket.settimeout(timeout)

import weblab.core.comm.admin_server as admin_server
from weblab.core.comm.user_server import USER_PROCESSING_FACADE_SERVER_ROUTE, DEFAULT_USER_PROCESSING_SERVER_ROUTE

class AdminRemoteFacadeServer(abstract_server.AbstractRemoteFacadeServer):
    SERVERS = (RemoteFacadeServerWSGI,)

    FACADE_WSGI_PORT             = admin_server.ADMIN_FACADE_JSON_PORT
    FACADE_WSGI_LISTEN           = admin_server.ADMIN_FACADE_JSON_LISTEN
    DEFAULT_FACADE_WSGI_LISTEN   = admin_server.DEFAULT_ADMIN_FACADE_JSON_LISTEN

    FACADE_SERVER_ROUTE          = USER_PROCESSING_FACADE_SERVER_ROUTE
    DEFAULT_SERVER_ROUTE         = DEFAULT_USER_PROCESSING_SERVER_ROUTE

    def _create_wsgi_remote_facade_manager(self, server, configuration_manager):
        self.application = AdministrationApplication(configuration_manager, server)
        return self.application.app

#############################################
# 
# The code below is only used for testing
# 

if __name__ == '__main__':
    from voodoo.configuration import ConfigurationManager
    cfg_manager = ConfigurationManager()
    cfg_manager.append_path('test/unit/configuration.py')


    DEBUG = True
    admin_app = AdministrationApplication(cfg_manager, None, bypass_authz = True)

    @admin_app.app.route('/')
    def index():
        return redirect('/weblab/administration')

    admin_app.app.run(debug=True, host = '0.0.0.0')

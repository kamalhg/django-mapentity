from functools import wraps

from django.utils.decorators import available_attrs, method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.http import last_modified as cache_last_modified
from django.utils.translation import ugettext_lazy as _
from django.core.exceptions import PermissionDenied
from django.core.cache import get_cache
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from django.views.generic.edit import BaseUpdateView
from django.views.generic.detail import BaseDetailView

from . import app_settings
from .helpers import user_has_perm
from . import models as mapentity_models


def view_permission_required(login_url=None, raise_exception=None):

    if raise_exception is None:
        raise_exception = (login_url is None)

    def check_perms(request, user, perm):
        # Check both authenticated and anonymous
        if user_has_perm(user, perm):
            return True

        if not user.is_anonymous() and raise_exception:
            raise PermissionDenied

        # As the last resort, redirects
        msg = _(u'Access to the requested resource is restricted. You have been redirected.')
        messages.warning(request, unicode(msg))
        return False

    def decorator(view_func):
        def _wrapped_view(self, request, *args, **kwargs):
            perm = self.get_view_perm()

            redirect_url = login_url
            if login_url in mapentity_models.ENTITY_KINDS:
                is_handle_object = issubclass(self.__class__, (BaseDetailView, BaseUpdateView))
                if is_handle_object:
                    view_subject = self.get_object()
                else:
                    view_subject = self.get_model()
                get_url_method = getattr(view_subject, 'get_{0}_url'.format(login_url))
                redirect_url = get_url_method()

            has_perm_decorator = user_passes_test(lambda u: check_perms(request, u, perm),
                                                  login_url=redirect_url,
                                                  redirect_field_name=None)
            cbv_user_has_perm = method_decorator(has_perm_decorator)

            @cbv_user_has_perm
            def decorated(self, request, *args, **kwargs):
                return view_func(self, request, *args, **kwargs)

            return decorated(self, request, *args, **kwargs)

        return _wrapped_view
    return decorator


def view_cache_latest():
    def decorator(view_func):
        def _wrapped_view(self, request, *args, **kwargs):
            view_model = self.get_model()

            cache_latest = cache_last_modified(lambda x: view_model.latest_updated())
            cbv_cache_latest = method_decorator(cache_latest)

            # The first decorator forces browser's cache revalidation.
            # The second one allows browser's cache revalidation.
            @method_decorator(never_cache)
            @cbv_cache_latest
            def decorated(self, request, *args, **kwargs):
                return view_func(self, request, *args, **kwargs)

            return decorated(self, request, *args, **kwargs)

        return _wrapped_view
    return decorator


def view_cache_response_content():
    def decorator(view_func):
        def _wrapped_method(self, *args, **kwargs):
            response_class = self.response_class
            response_kwargs = dict()

            # Do not (re)store cache if filters presents
            params = self.request.GET.keys()
            with_filters = all([not p.startswith('_') for p in params])
            if len(params) > 0 and with_filters:
                return view_func(self, *args, **kwargs)

            # Otherwise, restore from cache or store view result
            if hasattr(self, 'view_cache_key'):
                geojson_lookup = self.view_cache_key()
            else:
                view_model = self.get_model()
                language = self.request.LANGUAGE_CODE
                geojson_lookup = '%s_%s_json_layer' % (language,
                                                       view_model._meta.module_name)

            if hasattr(self, 'latest_updated'):
                latest_saved = self.latest_updated()
            else:
                latest_saved = view_model.latest_updated()

            geojson_cache = get_cache(app_settings['GEOJSON_LAYERS_CACHE_BACKEND'])
            latest_lookup = geojson_lookup + '_latest'
            latest_stored = geojson_cache.get(latest_lookup)

            if latest_stored and latest_saved:
                # Not empty and still valid
                if latest_stored >= latest_saved:
                    content = geojson_cache.get(geojson_lookup)
                    return response_class(content=content,
                                          **response_kwargs)

            response = view_func(self, *args, **kwargs)
            geojson_cache.set(latest_lookup, latest_saved)
            geojson_cache.set(geojson_lookup, response.content)
            return response

        return _wrapped_method
    return decorator


def save_history():
    """
    A decorator for class-based views, which save navigation history in
    session.
    """
    def decorator(view_func):
        @wraps(view_func, assigned=available_attrs(view_func))
        def _wrapped_view(self, request, *args, **kwargs):
            result = view_func(self, request, *args, **kwargs)

            # Stack list of request paths
            history = request.session.get('history', [])
            # Remove previous visits of this page
            history = [h for h in history if h['path'] != request.path]
            # Add this one and remove extras
            model = self.model or self.queryset.model
            history.insert(0, dict(title=unicode(self.get_title()),
                                   path=request.path,
                                   modelname=unicode(model._meta.object_name.lower())))
            if len(history) > app_settings['HISTORY_ITEMS_MAX']:
                history.pop()
            request.session['history'] = history

            return result
        return _wrapped_view
    return decorator

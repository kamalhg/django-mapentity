from django.conf.urls import patterns, url

from .views import map_screenshot, history_delete, JSSettings


urlpatterns = patterns('',
    url(r'^map_screenshot/$', map_screenshot, name='map_screenshot'),
    url(r'^history/delete/$', history_delete, name='history_delete'),
    # See default value in app_settings.JS_SETTINGS.
    # Will be overriden, most probably.
    url(r'^api/settings.json$', JSSettings.as_view(), name='js_settings'),
)

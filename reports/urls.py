from django.conf.urls import url

from . import views
urlpatterns = [
    url(r'^$', views.index, name='index'),

    # TODO: support numbers as well in this regex
    url(r'^job/(?P<job_name>[\w.-]+)/$',
        views.job,
        name='job'),
    url(r'^job/(?P<job_name>[\w.-]+)/(?P<build_number>[0-9]+)/$',
        views.build,
        name='build'),
    url(r'^job/(?P<job_name>[\w.-]+)/(?P<build_number>[0-9]+)/(?P<suite_name>[\w.-]+)/(?P<case_index>[0-9]+)/$',  # NOQA
        views.test,
        name='test')

    # url(r'^builds/([0-9]+)/$', views.builds, name='builds'),
    # url(r'^builds/([0-9]+)/timer$', views.timer_builds, name='timer_builds'),
    # url(r'^tests/([0-9]+)/$', views.tests, name='tests'),
    # url(r'^tests/([0-9]+)/failed&skipped/$', views.failed_tests, name='failed&skipped_tests'),
    # url(r'^logs/([0-9]+)/$', views.logs, name='logs'),
]


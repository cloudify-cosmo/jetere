from django.conf.urls import url

from . import views
from . import ajax

urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^ajax/$', ajax.unit_tests, name='unit_tests'),

    # TODO: support numbers as well in this regex
    url(r'^job/(?P<job_name>[\w.-]+)/$',
        views.job,
        name='job'),
    url(r'^job/(?P<job_name>[\w.-]+)/ajax/$',
        ajax.job_builds,
        name='job_builds'),

    url(r'^job/(?P<job_name>[\w.-]+)/(?P<build_number>[0-9]+)/$',
        views.build,
        name='build'),

    url(r'^job/(?P<job_name>[\w.-]+)/(?P<build_number>[0-9]+)/(?P<suite_name>[\w.-]+)/(?P<case_index>[0-9]+)/$',  # NOQA
        views.test,
        name='test'),
]


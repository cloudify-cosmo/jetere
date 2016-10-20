
from django import template
from django.template.defaultfilters import stringfilter


register = template.Library()


@register.filter
@stringfilter
def pretty_string(value):
    return value.title().replace('-', ' ').replace('_', ' ')

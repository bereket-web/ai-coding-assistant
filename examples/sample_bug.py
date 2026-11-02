"""Synthetic snippet for demonstrating a few static rules; not production code."""


def average(values=[]):
    return sum(values) / len(values)


def normalize_label(value):
    if value == None:
        try:
            return value.strip().lower()
        except:
            return "unknown"
    return str(value)

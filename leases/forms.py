from datetime import date

from django import forms

from .models import LeaseReport

MONTHS = [(m, date(2000, m, 1).strftime("%B")) for m in range(1, 13)]


class FriendlyNumberField(forms.IntegerField):
    """Accepts what people actually type: "$1,200", "1,200", "1200.00", " 1200 "."""

    widget = forms.TextInput

    def to_python(self, value):
        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").strip()
            if value.endswith(".00") or value.endswith(".0"):
                value = value.split(".")[0]
        return super().to_python(value)

    def widget_attrs(self, widget):
        attrs = super().widget_attrs(widget)
        attrs.pop("min", None)
        attrs.pop("max", None)
        attrs["inputmode"] = "numeric"
        return attrs


class MonthYearWidget(forms.MultiWidget):
    """Two dropdowns (Month, Year) instead of a date box, so nobody has to type a date format."""

    def __init__(self, attrs=None):
        this_year = date.today().year
        months = [("", "Month")] + MONTHS
        years = [("", "Year")] + [(y, y) for y in range(this_year + 1, 2009, -1)]
        widgets = [
            forms.Select(choices=months, attrs={"aria-label": "Month the lease started"}),
            forms.Select(choices=years, attrs={"aria-label": "Year the lease started"}),
        ]
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if isinstance(value, str):  # "2025-08", or "2025-" / "-08" when only one was picked
            parts = (value.split("-") + ["", ""])[:2]
            year = int(parts[0]) if parts[0].isdigit() else None
            month = int(parts[1]) if parts[1].isdigit() else None
            return [month, year]
        if value:
            return [value.month, value.year]
        return [None, None]

    def value_from_datadict(self, data, files, name):
        # Also accept a single "2025-08" value (used by the tests and the API).
        if data.get(name):
            return data[name]
        month, year = super().value_from_datadict(data, files, name)
        if not month and not year:
            return ""
        # If only one is picked, keep it so the person doesn't have to pick it again.
        return f"{year or ''}-{int(month):02d}" if month else f"{year}-"


class LeaseReportForm(forms.ModelForm):
    lease_start = forms.DateField(
        label="When did the lease start?",
        input_formats=["%Y-%m", "%Y-%m-%d"],
        error_messages={
            "required": "Pick the month and the year your lease started.",
            "invalid": "Pick the month and the year your lease started.",
        },
    )

    class Meta:
        model = LeaseReport
        fields = [
            "town",
            "property_type",
            "bedrooms",
            "monthly_rent",
            "per_person",
            "asking_rent",
            "utilities_included",
            "lease_start",
            "lease_months",
            "furnished",
            "square_feet",
            "walk_minutes",
        ]
        labels = {
            "town": "Which town?",
            "property_type": "What kind of place?",
            "bedrooms": "How many bedrooms?",
            "monthly_rent": "How much rent did you pay each month?",
            "per_person": "That amount was just my share (I paid for my own bedroom)",
            "asking_rent": "What did the listing say the rent was? (optional)",
            "utilities_included": "Utilities (water, power, internet) were included in the rent",
            "lease_months": "How long was the lease?",
            "furnished": "It came furnished",
            "square_feet": "About how many square feet? (optional)",
            "walk_minutes": "How long is the walk to campus? (optional)",
        }
        help_texts = {
            "monthly_rent": "Dollars per month. Example: 1200",
            "per_person": "Leave this unchecked if the amount above was the rent for the whole place.",
            "asking_rent": "Skip this if you don't remember. Example: 1250",
            "square_feet": "A guess is fine. Example: 850",
        }
        field_classes = {
            "monthly_rent": FriendlyNumberField,
            "asking_rent": FriendlyNumberField,
            "square_feet": FriendlyNumberField,
        }
        widgets = {
            "monthly_rent": forms.TextInput(attrs={"placeholder": "e.g. 1200"}),
            "asking_rent": forms.TextInput(attrs={"placeholder": "e.g. 1250"}),
            "square_feet": forms.TextInput(attrs={"placeholder": "e.g. 850"}),
        }
        error_messages = {
            "town": {"required": "Pick the town the place was in."},
            "bedrooms": {"required": "Pick how many bedrooms the place had."},
            "monthly_rent": {
                "required": "Enter the rent you paid each month, like 1200.",
                "invalid": "Enter the rent as a number, like 1200.",
                "min_value": "That looks too low. Enter the monthly rent in dollars, like 1200.",
                "max_value": "That looks too high. Enter the monthly rent in dollars, like 1200.",
            },
            "asking_rent": {
                "invalid": "Enter the rent as a number, like 1250.",
                "min_value": "That looks too low. Enter the monthly rent in dollars, like 1250.",
                "max_value": "That looks too high. Enter the monthly rent in dollars, like 1250.",
            },
            "square_feet": {
                "invalid": "Enter numbers only, like 850.",
                "min_value": "That looks too small. Leave it blank if you're not sure.",
                "max_value": "That looks too big. Leave it blank if you're not sure.",
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Built here so the year list is always current.
        self.fields["lease_start"].widget = MonthYearWidget()
        self.fields["town"].empty_label = "Choose a town"
        self.fields["bedrooms"].choices = [("", "Choose a number")] + list(self.fields["bedrooms"].choices)[1:]
        self.fields["walk_minutes"].choices = [("", "Not sure / skip")] + list(self.fields["walk_minutes"].choices)[1:]

    def clean_lease_start(self):
        start = self.cleaned_data["lease_start"].replace(day=1)
        today = date.today()
        if start.year < 2010:
            raise forms.ValidationError("Please only share leases from 2010 or later.")
        if start > date(today.year + 1, today.month, 1):
            raise forms.ValidationError("That start date is more than a year away. Pick when the lease actually started.")
        return start

    def clean(self):
        cleaned = super().clean()
        paid = cleaned.get("monthly_rent")
        asking = cleaned.get("asking_rent")
        # A huge gap is almost always a typo (extra zero, or mixing up your share vs. the whole place).
        if paid and asking and (paid > asking * 2 or asking > paid * 2):
            self.add_error(
                "asking_rent",
                "This is very different from the rent you paid. Check for a typo, "
                "or check the \"just my share\" box if you only paid for your own bedroom.",
            )
        return cleaned

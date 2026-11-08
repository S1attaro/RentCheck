from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse

from towns.models import BEDROOM_CHOICES, Town

PROPERTY_TYPES = [
    ("apartment", "Apartment"),
    ("student_building", "Student apartment building (per-bed leasing)"),
    ("house", "House"),
    ("duplex", "Duplex or townhouse"),
    ("room", "Room in a shared house"),
]

LEASE_LENGTHS = [(9, "9 months (school year)"), (10, "10 months"), (12, "12 months"), (0, "Other")]

WALK_TIMES = [
    (5, "Under 5 minutes"),
    (15, "5 to 15 minutes"),
    (30, "15 to 30 minutes"),
    (60, "More than 30 minutes / need a bus or car"),
]

# Reports this far from the town's typical rent are kept but left out of medians.
OUTLIER_LOW, OUTLIER_HIGH = 0.4, 2.5


class LeaseReport(models.Model):
    """What a student actually paid on a past lease.

    We never store names, addresses, or unit numbers. Only the town and the numbers.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lease_reports")
    town = models.ForeignKey(Town, on_delete=models.CASCADE, related_name="lease_reports")
    bedrooms = models.PositiveSmallIntegerField(choices=BEDROOM_CHOICES)
    monthly_rent = models.PositiveIntegerField(
        validators=[MinValueValidator(100), MaxValueValidator(10000)],
        help_text="What you paid each month, in dollars.",
    )
    asking_rent = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(100), MaxValueValidator(10000)],
        help_text="The price on the listing, if you remember it.",
    )
    per_person = models.BooleanField(
        default=False, help_text="Check this if the rent was per bed (per person), not for the whole unit."
    )
    utilities_included = models.BooleanField(default=False)
    lease_start = models.DateField(help_text="Month the lease started.")
    lease_months = models.PositiveSmallIntegerField(choices=LEASE_LENGTHS, default=12)
    property_type = models.CharField(max_length=20, choices=PROPERTY_TYPES, default="apartment")
    furnished = models.BooleanField(default=False)
    square_feet = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(100), MaxValueValidator(10000)]
    )
    walk_minutes = models.PositiveSmallIntegerField(
        choices=WALK_TIMES, null=True, blank=True, verbose_name="Walk to campus"
    )
    flagged = models.BooleanField(
        default=False, help_text="Far from the town's typical rent. Kept, but left out of medians."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-lease_start"]

    def __str__(self):
        return f"{self.town.name}, {self.get_bedrooms_display()}, ${self.monthly_rent}"

    def get_absolute_url(self):
        return reverse("leases:edit", args=[self.pk])

    @property
    def unit_rent(self):
        """Rent for the whole unit, so per-bed and whole-unit reports can be compared."""
        if self.per_person and self.bedrooms > 0:
            return self.monthly_rent * self.bedrooms
        return self.monthly_rent

    def check_outlier(self, typical_rent):
        """Flag reports that are way off the town's typical rent (likely a typo)."""
        if not typical_rent:
            self.flagged = False
            return
        ratio = self.unit_rent / typical_rent
        self.flagged = ratio < OUTLIER_LOW or ratio > OUTLIER_HIGH

    @property
    def paid_vs_asking(self):
        if not self.asking_rent:
            return None
        return self.monthly_rent - self.asking_rent

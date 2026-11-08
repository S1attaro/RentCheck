from django.db import models
from django.urls import reverse

# Plain names, since these show up on the site.
SOURCE_CHOICES = [
    ("zillow", "Zillow asking rents"),
    ("rentcast", "Current listings (RentCast)"),
    ("census", "What renters pay (Census)"),
    ("hud", "Government fair rent (HUD)"),
    ("ipeds", "Students enrolled (College Scorecard)"),
    ("demo", "Demo data (not real)"),
]

# What each source actually measures, shown next to the numbers.
SOURCE_NOTES = {
    "zillow": "The typical price on new listings in town, for all sizes. Updated monthly.",
    "rentcast": "The middle price of places listed for rent near campus right now. The most current number.",
    "census": "What renters in town actually pay, with utilities. It's averaged over 5 years, so it runs a year or two behind.",
    "hud": "The rent the government uses for housing vouchers in this county. Usually lower than what students pay, so think of it as a floor.",
    "ipeds": "Undergrads enrolled at the university.",
    "demo": "Placeholder numbers, not real data.",
}

# Yearly sources only have a year, not a real month.
YEARLY_SOURCES = {"census", "hud"}

BEDROOM_CHOICES = [
    (0, "Studio"),
    (1, "1 bedroom"),
    (2, "2 bedrooms"),
    (3, "3 bedrooms"),
    (4, "4 bedrooms"),
    (5, "5+ bedrooms"),
]


class Town(models.Model):
    name = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    university = models.CharField(max_length=150)
    slug = models.SlugField(unique=True)

    # How each data source names this town. All comma separated where there can be more than one.
    zillow_names = models.CharField(max_length=200, blank=True, help_text='e.g. "Champaign,Urbana"')
    census_places = models.CharField(max_length=200, blank=True, help_text='e.g. "Champaign city,Urbana city"')
    county = models.CharField(max_length=100, blank=True, help_text='For HUD, e.g. "Champaign County"')
    zip_codes = models.CharField(max_length=100, blank=True, help_text="ZIPs near campus, main one first")
    scorecard_id = models.CharField(max_length=10, blank=True, help_text="The school's IPEDS unit ID")

    # Filled in by fetch_scorecard
    school_size = models.PositiveIntegerField(null=True, blank=True)
    school_offcampus_cost = models.PositiveIntegerField(
        null=True, blank=True, help_text="School's own estimate of off-campus room and board per year"
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name}, {self.state}"

    def get_absolute_url(self):
        return reverse("towns:detail", args=[self.slug])

    @property
    def zip_list(self):
        return [z.strip() for z in self.zip_codes.split(",") if z.strip()]


class RentPoint(models.Model):
    """Typical monthly rent for a town in one month.

    bedrooms is empty when the number covers all unit sizes.
    """

    town = models.ForeignKey(Town, on_delete=models.CASCADE, related_name="rent_points")
    month = models.DateField(help_text="First day of the month")
    bedrooms = models.PositiveSmallIntegerField(choices=BEDROOM_CHOICES, null=True, blank=True)
    rent = models.DecimalField(max_digits=8, decimal_places=2)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)

    class Meta:
        ordering = ["town", "month"]
        constraints = [
            models.UniqueConstraint(
                fields=["town", "month", "bedrooms", "source"], name="one_rent_point_per_month"
            )
        ]

    def __str__(self):
        size = self.get_bedrooms_display() if self.bedrooms is not None else "all units"
        return f"{self.town.name} {self.month:%Y-%m} {size}: ${self.rent}"


class EnrollmentPoint(models.Model):
    """Student counts by year. "ipeds" = enrolled at the school, "census" = living in town."""

    town = models.ForeignKey(Town, on_delete=models.CASCADE, related_name="enrollment_points")
    year = models.PositiveSmallIntegerField()
    students = models.PositiveIntegerField()
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)

    class Meta:
        ordering = ["town", "year"]
        constraints = [
            models.UniqueConstraint(fields=["town", "year", "source"], name="one_enrollment_per_year_source")
        ]

    def __str__(self):
        return f"{self.town.name} {self.year}: {self.students:,} students ({self.source})"


class Listing(models.Model):
    """A current rental listing from RentCast. Used for "similar places" in the fair rent check."""

    town = models.ForeignKey(Town, on_delete=models.CASCADE, related_name="listings")
    external_id = models.CharField(max_length=200, unique=True)
    address = models.CharField(max_length=300)
    zip_code = models.CharField(max_length=10, blank=True)
    property_type = models.CharField(max_length=50, blank=True)
    bedrooms = models.PositiveSmallIntegerField(null=True, blank=True)
    bathrooms = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    square_feet = models.PositiveIntegerField(null=True, blank=True)
    price = models.PositiveIntegerField(help_text="Listed monthly rent")
    listed_date = models.DateField(null=True, blank=True)
    days_on_market = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["price"]

    def __str__(self):
        return f"{self.address}: ${self.price}"


class ApiCall(models.Model):
    """Every call to an outside API. Used to stay under free limits and for monitoring."""

    service = models.CharField(max_length=20)
    called_at = models.DateTimeField(auto_now_add=True)
    url = models.CharField(max_length=500)
    ok = models.BooleanField(default=False)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-called_at"]

    def __str__(self):
        return f"{self.service} {self.called_at:%Y-%m-%d %H:%M} {'ok' if self.ok else 'failed'}"


class DataImport(models.Model):
    """One row per data refresh, so the site can say where numbers came from and when."""

    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    finished_at = models.DateTimeField(auto_now_add=True)
    rows = models.PositiveIntegerField(default=0)
    detail = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-finished_at"]

    def __str__(self):
        return f"{self.get_source_display()} on {self.finished_at:%Y-%m-%d}: {self.rows} rows"

from statistics import median

# Hide numbers until enough students report, so one person's lease can't be picked out.
MIN_REPORTS = 3


def reported_summary(town, bedrooms=None):
    reports = town.lease_reports.filter(flagged=False)
    if bedrooms is not None:
        reports = reports.filter(bedrooms=bedrooms)
    reports = list(reports)
    count = len(reports)

    summary = {"count": count, "min_reports": MIN_REPORTS, "enough": count >= MIN_REPORTS}
    if not summary["enough"]:
        return summary

    summary["median_unit_rent"] = median(r.unit_rent for r in reports)
    gaps = [r.paid_vs_asking for r in reports if r.paid_vs_asking is not None]
    summary["median_paid_vs_asking"] = median(gaps) if len(gaps) >= MIN_REPORTS else None
    return summary

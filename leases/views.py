from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from towns import stats
from towns.models import Town

from .forms import LeaseReportForm
from .models import LeaseReport


class OwnReportsMixin(LoginRequiredMixin):
    """Users can only see and change their own reports. Others get a 404."""

    def get_queryset(self):
        return LeaseReport.objects.filter(user=self.request.user).select_related("town")


def save_report(form):
    report = form.save(commit=False)
    report.check_outlier(stats.typical_rent(report.town, report.bedrooms))
    report.save()
    return report


class MyReportsView(OwnReportsMixin, ListView):
    template_name = "leases/my_reports.html"
    context_object_name = "reports"


class ReportCreateView(LoginRequiredMixin, CreateView):
    model = LeaseReport
    form_class = LeaseReportForm
    template_name = "leases/report_form.html"
    success_url = reverse_lazy("leases:mine")

    def get_initial(self):
        # Coming from a town page or a rent check: ?town=urbana-champaign
        initial = super().get_initial()
        town = Town.objects.filter(slug=self.request.GET.get("town", "")).first()
        if town:
            initial["town"] = town
        return initial

    def form_valid(self, form):
        form.instance.user = self.request.user
        self.object = save_report(form)
        if self.object.flagged:
            messages.warning(self.request, "Saved, but this rent is far from the town's typical rent, so it won't count toward the averages. Double check the numbers.")
        else:
            messages.success(self.request, "Thanks! Your lease was added. Only totals are shown to others.")
        return redirect(self.success_url)


class ReportUpdateView(OwnReportsMixin, UpdateView):
    form_class = LeaseReportForm
    template_name = "leases/report_form.html"
    success_url = reverse_lazy("leases:mine")

    def form_valid(self, form):
        self.object = save_report(form)
        messages.success(self.request, "Lease report updated.")
        return redirect(self.success_url)


class ReportDeleteView(OwnReportsMixin, DeleteView):
    template_name = "leases/report_confirm_delete.html"
    success_url = reverse_lazy("leases:mine")

    def form_valid(self, form):
        messages.success(self.request, "Lease report deleted.")
        return super().form_valid(form)

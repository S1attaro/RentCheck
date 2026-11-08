from django.contrib.auth.forms import UserCreationForm


class SignupForm(UserCreationForm):
    """Django's sign up form with plainer labels and hints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Pick a username"
        self.fields["username"].help_text = "Anything you'll remember. It doesn't need to be your real name."
        self.fields["password1"].label = "Pick a password"
        self.fields["password1"].help_text = "At least 8 characters. Not all numbers, and not something common like password123."
        self.fields["password2"].label = "Type the password again"
        self.fields["password2"].help_text = ""

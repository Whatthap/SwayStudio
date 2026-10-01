import re

from django import forms
from django.conf import settings
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import CustomerAddress, ProductVariant, Review


PROVINCES = (
    ('Phnom Penh', 'Phnom Penh'), ('Banteay Meanchey', 'Banteay Meanchey'),
    ('Battambang', 'Battambang'), ('Kampong Cham', 'Kampong Cham'),
    ('Kampong Chhnang', 'Kampong Chhnang'), ('Kampong Speu', 'Kampong Speu'),
    ('Kampong Thom', 'Kampong Thom'), ('Kampot', 'Kampot'), ('Kandal', 'Kandal'),
    ('Kep', 'Kep'), ('Koh Kong', 'Koh Kong'), ('Kratie', 'Kratie'),
    ('Mondulkiri', 'Mondulkiri'), ('Oddar Meanchey', 'Oddar Meanchey'),
    ('Pailin', 'Pailin'), ('Preah Sihanouk', 'Preah Sihanouk'),
    ('Preah Vihear', 'Preah Vihear'), ('Prey Veng', 'Prey Veng'),
    ('Pursat', 'Pursat'), ('Ratanakiri', 'Ratanakiri'), ('Siem Reap', 'Siem Reap'),
    ('Stung Treng', 'Stung Treng'), ('Svay Rieng', 'Svay Rieng'),
    ('Takeo', 'Takeo'), ('Tboung Khmum', 'Tboung Khmum'),
)


class CheckoutForm(forms.Form):
    full_name = forms.CharField(max_length=120, label='Full name')
    email = forms.EmailField()
    phone = forms.CharField(max_length=30, label='Cambodian phone number')
    address = forms.CharField(max_length=200, label='Street address')
    district = forms.CharField(max_length=100, required=False)
    city = forms.CharField(max_length=100, label='Commune / city')
    province = forms.ChoiceField(choices=PROVINCES, initial='Phnom Penh')
    postal_code = forms.CharField(max_length=20, required=False, label='Postal code (optional)')
    notes = forms.CharField(required=False, label='Delivery notes', widget=forms.Textarea)
    coupon_code = forms.CharField(max_length=40, required=False, label='Discount code')
    payment_method = forms.ChoiceField(choices=(("cod", "Cash on delivery"),))
    save_address = forms.BooleanField(required=False, label='Save this delivery address to my account')

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if settings.PAYWAY_MERCHANT_ID and settings.PAYWAY_API_KEY:
            self.fields['payment_method'].choices += (("payway", "ABA PayWay (ABA Pay / KHQR / cards)"),)
        if user and user.is_authenticated and not self.is_bound:
            self.initial.setdefault('full_name', user.get_full_name())
            self.initial.setdefault('email', user.email)
            address = CustomerAddress.objects.filter(user=user).first()
            if address:
                for field in ('phone', 'address', 'district', 'city', 'province', 'postal_code'):
                    self.initial.setdefault(field, getattr(address, field))

    def clean_phone(self):
        phone = re.sub(r'[\s()-]', '', self.cleaned_data['phone'])
        if not re.fullmatch(r'(?:\+855|0)[1-9]\d{7,9}', phone):
            raise forms.ValidationError('Enter a Cambodian number, for example +855 12 345 678.')
        return phone


class CustomerRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'username', 'email', 'password1', 'password2')

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account already uses this email address.')
        return email


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ('rating', 'body')
        widgets = {'rating': forms.Select(choices=((5, '5 stars'), (4, '4 stars'), (3, '3 stars'), (2, '2 stars'), (1, '1 star')))}
        labels = {'rating': 'Your rating', 'body': 'Your review'}


class VariantForm(forms.Form):
    variant = forms.ModelChoiceField(queryset=ProductVariant.objects.none(), empty_label='Choose size and color')

    def __init__(self, product, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['variant'].queryset = product.variants.filter(stock__gt=0)
        self.fields['variant'].label_from_instance = lambda variant: f'{variant.size} / {variant.color_name} — {variant.stock} available'
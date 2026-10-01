from django.urls import path

from . import commerce as views

app_name = 'shop'

urlpatterns = [
    path('', views.home, name='home'),
    path('products/<slug:slug>/', views.product_detail, name='product_detail'),
    path('cart/<slug:slug>/', views.cart_change, name='cart_change'),
    path('checkout/', views.checkout, name='checkout'),
    path('order/<uuid:public_id>/', views.order_success, name='order_success'),
    path('payment/payway/<uuid:public_id>/', views.payway_redirect, name='payway_redirect'),
    path('payment/payway/callback/', views.payway_callback, name='payway_callback'),
    path('account/register/', views.register, name='register'),
    path('account/login/', views.login_view, name='login'),
    path('account/logout/', views.logout_view, name='logout'),
    path('account/', views.account, name='account'),
    path('favorites/<slug:slug>/', views.favorite_toggle, name='favorite_toggle'),
    path('policies/<slug:page>/', views.policy, name='policy'),
    path('contact/', views.contact, name='contact'),
]
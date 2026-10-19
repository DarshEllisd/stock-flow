from django.urls import path
from core import views
from core.chatbot_view import chatbot
from core.google_oauth import google_login, google_callback
urlpatterns = [
    path('', views.home, name='home'),
    path('signout/', views.signout, name='signout'),

    path('auth/signin/', views.signin_page, name='signin_page'),
    path('auth/signup/', views.signup_page, name='signup_page'),
    path('auth/signout/', views.signout_page, name='signout_page'),
    path('auth/google/', google_login, name='google_login'),
    path('auth/google/callback/', google_callback, name='google_callback'),

    # Abhi this is just dummy in the views.py, change it when needed
    path('products/', views.products, name='products'),
    path('items/', views.items, name='items'),
    path('items/sold-out/', views.sold_out_items, name='sold_out_items'),
    path('items/<int:product_id>/', views.item_detail, name='item_detail'),
    path('inventory/', views.inventory, name='inventory'),
    path('inventory/edit/<int:product_id>/', views.inventory, name='edit_inventory'),
    path('add-address/', views.add_address, name='add_address'),


    path('orders/', views.order_history, name='order_history'),
 path('profile/',                              views.profile,             name='profile'),
path('profile/update/',                       views.update_profile,      name='update_profile'),
path('profile/delete-account/',               views.delete_account,      name='delete_account'),
path('orders/<int:order_id>/delete/',         views.delete_order,        name='delete_order'),
path('addresses/<int:address_id>/delete/',    views.delete_address,      name='delete_address'),
path('addresses/<int:address_id>/default/',   views.set_default_address, name='set_default_address'),

    path('cart/',                          views.cart,        name='cart'),
    path('cart/remove/<int:product_id>/',  views.cart_remove, name='cart_remove'),
    path('cart/update/<int:product_id>/',  views.cart_update, name='cart_update'),
    path('checkout/',                      views.checkout,    name='checkout'),

    # Notifications & Approval Workflow
    path('notifications/',                              views.notifications,              name='notifications'),
    path('notifications/mark-all-read/',                views.mark_all_notifications_read, name='mark_all_notifications_read'),
    path('notifications/<int:notification_id>/read/',   views.mark_notification_read,      name='mark_notification_read'),
    path('order-item/<int:item_id>/approve/',           views.seller_approve_item,         name='seller_approve_item'),
    path('order-item/<int:item_id>/reject/',            views.seller_reject_item,          name='seller_reject_item'),
    path('chatbot/',chatbot,name='chatbot'),

    # Wallet
    path('wallet/',            views.wallet_page, name='wallet'),
    path('wallet/add-funds/',  views.add_funds,   name='add_funds'),
]
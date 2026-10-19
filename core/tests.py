import base64
import json
import time
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from core.models import (
	Address, Buyer, Inventory, Notification, Order, OrderItem, Product, Seller, Transaction, Wallet,
)


def _fake_id_token(**claims):
	payload = {
		'iss': 'https://accounts.google.com',
		'aud': 'test-client-id',
		'exp': int(time.time()) + 300,
		'email': 'alice@example.com',
		'email_verified': True,
		'name': 'Alice Google',
	}
	payload.update(claims)
	encode = lambda data: base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b'=').decode()
	return f"{encode({'alg': 'RS256'})}.{encode(payload)}.signature"


@override_settings(GOOGLE_CLIENT_ID='test-client-id', GOOGLE_CLIENT_SECRET='test-secret')
class GoogleAuthTests(TestCase):
	def _start_login(self, user_type='buyer'):
		response = self.client.get(reverse('google_login'), {'user_type': user_type})
		return response, self.client.session.get('google_oauth')

	def _callback(self, id_token, state=None):
		_, pending = self._start_login(self._user_type)
		with mock.patch('core.google_oauth._exchange_code', return_value={'id_token': id_token}) as exchange:
			response = self.client.get(
				reverse('google_callback'),
				{'code': 'auth-code', 'state': state or pending['state']},
			)
		return response, exchange

	_user_type = 'buyer'

	def test_login_redirects_to_google_with_state_and_pkce(self):
		response, pending = self._start_login('seller')

		self.assertEqual(response.status_code, 302)
		url = urlparse(response['Location'])
		params = parse_qs(url.query)
		self.assertEqual(url.netloc, 'accounts.google.com')
		self.assertEqual(params['client_id'], ['test-client-id'])
		self.assertEqual(params['state'], [pending['state']])
		self.assertEqual(params['code_challenge_method'], ['S256'])
		self.assertTrue(params['code_challenge'][0])
		self.assertTrue(params['redirect_uri'][0].endswith('/auth/google/callback/'))
		self.assertEqual(pending['user_type'], 'seller')

	def test_login_rejects_invalid_user_type(self):
		response, pending = self._start_login('admin')

		self.assertRedirects(response, reverse('signin_page'))
		self.assertIsNone(pending)

	def test_callback_creates_buyer_with_wallet_and_signs_in(self):
		response, exchange = self._callback(_fake_id_token())

		self.assertRedirects(response, reverse('home'))
		buyer = Buyer.objects.get(email='alice@example.com')
		self.assertEqual(buyer.name, 'Alice Google')
		self.assertEqual(buyer.phone, '')
		self.assertIsNotNone(buyer.wallet)
		self.assertEqual(self.client.session['user_id'], buyer.id)
		self.assertEqual(self.client.session['user_type'], 'buyer')
		self.assertNotIn('google_oauth', self.client.session)
		self.assertEqual(exchange.call_args.args[0], 'auth-code')

	def test_callback_signs_existing_seller_into_their_account(self):
		seller = Seller.objects.create(name='Sam Seller', email='sam@example.com')
		self._user_type = 'seller'

		response, _ = self._callback(_fake_id_token(email='SAM@example.com', name='Other Name'))

		self.assertRedirects(response, reverse('home'))
		self.assertEqual(Seller.objects.filter(email='sam@example.com').count(), 1)
		self.assertFalse(Buyer.objects.filter(email='sam@example.com').exists())
		self.assertEqual(self.client.session['user_id'], seller.id)
		self.assertEqual(self.client.session['user_name'], 'Sam Seller')

	def test_callback_rejects_state_mismatch(self):
		response, exchange = self._callback(_fake_id_token(), state='forged-state')

		self.assertRedirects(response, reverse('signin_page'))
		exchange.assert_not_called()
		self.assertFalse(Buyer.objects.exists())
		self.assertIsNone(self.client.session.get('user_id'))

	def test_callback_rejects_unverified_email(self):
		response, _ = self._callback(_fake_id_token(email_verified=False))

		self.assertRedirects(response, reverse('signin_page'))
		self.assertFalse(Buyer.objects.exists())

	def test_callback_rejects_token_for_another_app(self):
		response, _ = self._callback(_fake_id_token(aud='someone-else'))

		self.assertRedirects(response, reverse('signin_page'))
		self.assertFalse(Buyer.objects.exists())

	def test_callback_cannot_be_replayed(self):
		_, pending = self._start_login('buyer')
		params = {'code': 'auth-code', 'state': pending['state']}
		with mock.patch('core.google_oauth._exchange_code', return_value={'id_token': _fake_id_token()}):
			self.client.get(reverse('google_callback'), params)
			self.client.post(reverse('signout'), data='{}', content_type='application/json')
			replay = self.client.get(reverse('google_callback'), params)

		self.assertRedirects(replay, reverse('signin_page'))
		self.assertIsNone(self.client.session.get('user_id'))


class AccountSessionTests(TestCase):
	def setUp(self):
		self.client = Client(enforce_csrf_checks=True)

	def _sign_in(self, user, user_type):
		session = self.client.session
		session['user_id'] = user.id
		session['user_type'] = user_type
		session['user_name'] = user.name
		session.save()

	def test_signout_clears_session_and_returns_200(self):
		seller = Seller.objects.create(name='Sam Seller', email='sam@example.com')
		self._sign_in(seller, 'seller')

		response = self.client.post(reverse('signout'), data='{}', content_type='application/json')

		self.assertEqual(response.status_code, 200)
		self.assertIsNone(self.client.session.get('user_id'))

	def test_privacy_and_terms_pages_are_public(self):
		privacy = self.client.get(reverse('privacy_policy'))
		terms = self.client.get(reverse('terms_of_service'))

		self.assertContains(privacy, 'Privacy Policy')
		self.assertContains(terms, 'Terms of Service')

	def test_signup_page_redirects_to_signin_page(self):
		response = self.client.get(reverse('signup_page'))
		self.assertRedirects(response, reverse('signin_page'))

	def test_update_profile_saves_name_and_phone_but_not_email(self):
		buyer = Buyer.objects.create(name='Old Name', email='buyer@example.com')
		self._sign_in(buyer, 'buyer')
		self.client.get(reverse('profile'))
		csrf_token = self.client.cookies['csrftoken'].value

		self.client.post(
			reverse('update_profile'),
			{'name': 'New Name', 'phone': '9876543210', 'email': 'hacker@example.com'},
			HTTP_X_CSRFTOKEN=csrf_token,
		)

		buyer.refresh_from_db()
		self.assertEqual(buyer.name, 'New Name')
		self.assertEqual(buyer.phone, '9876543210')
		self.assertEqual(buyer.email, 'buyer@example.com')

	def test_delete_account_removes_buyer_from_database(self):
		buyer = Buyer.objects.create(
			name='Delete Buyer',
			email='delete-buyer@example.com',
			phone='1234567890',
		)
		self._sign_in(buyer, 'buyer')

		self.client.get(reverse('profile'))
		csrf_token = self.client.cookies['csrftoken'].value

		response = self.client.post(reverse('delete_account'), HTTP_X_CSRFTOKEN=csrf_token)

		self.assertRedirects(response, reverse('signin_page'))
		self.assertFalse(Buyer.objects.filter(id=buyer.id).exists())
		self.assertIsNone(self.client.session.get('user_id'))

	def test_delete_account_removes_seller_from_database(self):
		seller = Seller.objects.create(
			name='Delete Seller',
			email='delete-seller@example.com',
			phone='1234567890',
		)
		self._sign_in(seller, 'seller')

		self.client.get(reverse('profile'))
		csrf_token = self.client.cookies['csrftoken'].value

		response = self.client.post(reverse('delete_account'), HTTP_X_CSRFTOKEN=csrf_token)

		self.assertRedirects(response, reverse('signin_page'))
		self.assertFalse(Seller.objects.filter(id=seller.id).exists())
		self.assertIsNone(self.client.session.get('user_id'))


class AccountDeletionTests(TestCase):
	def setUp(self):
		self.buyer = Buyer.objects.create(name='Bea Buyer', email='bea@example.com', wallet=Wallet.objects.create(balance=500))
		self.seller = Seller.objects.create(name='Sid Seller', email='sid@example.com', wallet=Wallet.objects.create(balance=200))
		Transaction.objects.create(wallet=self.buyer.wallet, transaction_type='add_funds', amount=500, balance_after=500, description='seed')
		Transaction.objects.create(wallet=self.seller.wallet, transaction_type='credit', amount=200, balance_after=200, description='seed')
		self.warehouse = Address.objects.create(seller=self.seller, line1='Hub', city='Pune', state='MH', postal_code='411001', country='India')
		self.product = Product.objects.create(seller=self.seller, name='Lamp', description='Desk lamp', price=100, sku='LAMP-1')
		Inventory.objects.create(product=self.product, quantity=5, warehouse_location=self.warehouse)

	def _place_order(self, status='Confirmed', item_status='Approved'):
		address = Address.objects.create(buyer=self.buyer, line1='Home', city='Pune', state='MH', postal_code='411002', country='India')
		order = Order.objects.create(buyer=self.buyer, address=address, total_amount=100, status=status)
		item = OrderItem.objects.create(order=order, product=self.product, quantity=1, unit_price=100, line_total=100, status=item_status)
		Notification.objects.create(buyer=self.buyer, order=order, notification_type='order_placed', message='placed')
		Notification.objects.create(seller=self.seller, order=order, order_item=item, notification_type='approval_request', message='approve')
		return order, address

	def _delete(self, user, user_type):
		session = self.client.session
		session['user_id'] = user.id
		session['user_type'] = user_type
		session['user_name'] = user.name
		session.save()
		return self.client.post(reverse('delete_account'))

	def test_buyer_without_orders_is_deleted_with_wallet(self):
		wallet_id = self.buyer.wallet_id

		response = self._delete(self.buyer, 'buyer')

		self.assertRedirects(response, reverse('signin_page'))
		self.assertFalse(Buyer.objects.filter(id=self.buyer.id).exists())
		self.assertFalse(Wallet.objects.filter(id=wallet_id).exists())
		self.assertFalse(Transaction.objects.filter(wallet_id=wallet_id).exists())

	def test_seller_without_sales_is_deleted_with_wallet_and_products(self):
		wallet_id = self.seller.wallet_id

		response = self._delete(self.seller, 'seller')

		self.assertRedirects(response, reverse('signin_page'))
		self.assertFalse(Seller.objects.filter(id=self.seller.id).exists())
		self.assertFalse(Wallet.objects.filter(id=wallet_id).exists())
		self.assertFalse(Product.objects.filter(id=self.product.id).exists())

	def test_deleted_seller_product_images_are_removed_from_storage(self):
		Product.objects.filter(id=self.product.id).update(image='product_images/lamp-abc.jpg')

		with mock.patch('core.views.default_storage.delete') as delete_file, \
				self.captureOnCommitCallbacks(execute=True):
			self._delete(self.seller, 'seller')

		delete_file.assert_called_once_with('product_images/lamp-abc.jpg')

	def test_buyer_with_past_orders_is_anonymized_and_history_kept(self):
		order, order_address = self._place_order()
		spare_address = Address.objects.create(buyer=self.buyer, line1='Spare', city='Pune', state='MH', postal_code='411003', country='India')
		wallet_id = self.buyer.wallet_id

		response = self._delete(self.buyer, 'buyer')

		self.assertRedirects(response, reverse('signin_page'))
		self.assertIsNone(self.client.session.get('user_id'))
		buyer = Buyer.objects.get(id=self.buyer.id)
		self.assertEqual(buyer.name, 'Deleted user')
		self.assertNotEqual(buyer.email, 'bea@example.com')
		self.assertEqual(buyer.phone, '')
		self.assertIsNone(buyer.wallet_id)
		self.assertFalse(Wallet.objects.filter(id=wallet_id).exists())
		self.assertFalse(Transaction.objects.filter(wallet_id=wallet_id).exists())
		self.assertFalse(Notification.objects.filter(buyer=buyer).exists())
		self.assertFalse(Address.objects.filter(id=spare_address.id).exists())
		# The seller's view of the sale stays intact.
		self.assertTrue(Order.objects.filter(id=order.id).exists())
		self.assertTrue(Address.objects.filter(id=order_address.id).exists())
		self.assertTrue(Notification.objects.filter(seller=self.seller).exists())

	def test_seller_with_sales_is_anonymized_and_buyer_orders_kept(self):
		order, _ = self._place_order()
		unsold = Product.objects.create(seller=self.seller, name='Rug', description='Floor rug', price=50, sku='RUG-1')
		wallet_id = self.seller.wallet_id

		response = self._delete(self.seller, 'seller')

		self.assertRedirects(response, reverse('signin_page'))
		seller = Seller.objects.get(id=self.seller.id)
		self.assertEqual(seller.name, 'Deleted user')
		self.assertNotEqual(seller.email, 'sid@example.com')
		self.assertIsNone(seller.wallet_id)
		self.assertFalse(Wallet.objects.filter(id=wallet_id).exists())
		self.assertFalse(Notification.objects.filter(seller=seller).exists())
		self.assertFalse(Product.objects.filter(id=unsold.id).exists())
		self.assertFalse(Address.objects.filter(id=self.warehouse.id).exists())
		# Sold product stays for the buyer's order history but is no longer on sale.
		self.assertTrue(Product.objects.filter(id=self.product.id).exists())
		self.assertFalse(Inventory.objects.filter(product=self.product).exists())
		self.assertTrue(OrderItem.objects.filter(order=order, product=self.product).exists())

	def test_deleted_email_can_sign_up_again(self):
		self._place_order()
		self._delete(self.buyer, 'buyer')

		self.assertFalse(Buyer.objects.filter(email='bea@example.com').exists())
		Buyer.objects.create(name='Bea Again', email='bea@example.com')

	def test_buyer_with_pending_order_cannot_delete(self):
		self._place_order(status='Pending', item_status='Pending')

		response = self._delete(self.buyer, 'buyer')

		self.assertRedirects(response, reverse('profile'), fetch_redirect_response=False)
		self.assertEqual(Buyer.objects.get(id=self.buyer.id).email, 'bea@example.com')
		self.assertEqual(self.client.session.get('user_id'), self.buyer.id)

	def test_seller_with_pending_approval_cannot_delete(self):
		self._place_order(status='Pending', item_status='Pending')

		response = self._delete(self.seller, 'seller')

		self.assertRedirects(response, reverse('profile'), fetch_redirect_response=False)
		self.assertEqual(Seller.objects.get(id=self.seller.id).email, 'sid@example.com')


class ItemsPageAuthTests(TestCase):
	def test_items_redirects_home_when_not_logged_in(self):
		response = self.client.get(reverse('items'))
		self.assertRedirects(response, reverse('home'))

	def test_items_renders_for_valid_buyer_session(self):
		buyer = Buyer.objects.create(
			name='Buyer One',
			email='buyer1@example.com',
			phone='1234567890',
			password='x',
		)

		session = self.client.session
		session['user_id'] = buyer.id
		session['user_type'] = 'buyer'
		session['user_name'] = buyer.name
		session.save()

		response = self.client.get(reverse('items'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'StockFlow Item List')

	def test_items_renders_for_valid_seller_session(self):
		seller = Seller.objects.create(
			name='Seller One',
			email='seller1@example.com',
			phone='1234567890',
			password='x',
		)

		session = self.client.session
		session['user_id'] = seller.id
		session['user_type'] = 'seller'
		session['user_name'] = seller.name
		session.save()

		response = self.client.get(reverse('items'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'StockFlow Item List')

	def test_items_redirects_home_for_invalid_user_type(self):
		session = self.client.session
		session['user_id'] = 1
		session['user_type'] = 'admin'
		session['user_name'] = 'Invalid'
		session.save()

		response = self.client.get(reverse('items'))
		self.assertRedirects(response, reverse('home'))

	def test_items_redirects_home_if_session_user_missing_in_db(self):
		session = self.client.session
		session['user_id'] = 99999
		session['user_type'] = 'buyer'
		session['user_name'] = 'Ghost'
		session.save()

		response = self.client.get(reverse('items'))
		self.assertRedirects(response, reverse('home'))


class SellerInventoryPageTests(TestCase):
	def test_inventory_redirects_home_for_unauthenticated_user(self):
		response = self.client.get(reverse('inventory'))
		self.assertRedirects(response, reverse('home'))

	def test_inventory_redirects_home_for_buyer(self):
		buyer = Buyer.objects.create(
			name='Buyer Only',
			email='buyer-only@example.com',
			phone='1234567890',
			password='x',
		)

		session = self.client.session
		session['user_id'] = buyer.id
		session['user_type'] = 'buyer'
		session['user_name'] = buyer.name
		session.save()

		response = self.client.get(reverse('inventory'))
		self.assertRedirects(response, reverse('home'))

	def test_inventory_renders_for_seller(self):
		seller = Seller.objects.create(
			name='Seller Access',
			email='seller-access@example.com',
			phone='1234567890',
			password='x',
		)

		session = self.client.session
		session['user_id'] = seller.id
		session['user_type'] = 'seller'
		session['user_name'] = seller.name
		session.save()

		response = self.client.get(reverse('inventory'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Seller Item Creation')

	def test_inventory_post_creates_product_and_inventory_for_seller(self):
		seller = Seller.objects.create(
			name='Seller Create',
			email='seller-create@example.com',
			phone='1234567890',
			password='x',
		)

		# Create an address for the seller to use as warehouse location
		from core.models import Address
		address = Address.objects.create(
			seller=seller,
			line1='North Hub',
			city='Mumbai',
			state='Maharashtra',
			postal_code='400001',
			country='India',
		)

		session = self.client.session
		session['user_id'] = seller.id
		session['user_type'] = 'seller'
		session['user_name'] = seller.name
		session.save()

		response = self.client.post(
			reverse('inventory'),
			data={
				'name': 'Widget Pro',
				'description': 'Premium widget for testing.',
				'image_url': 'https://example.com/widget.jpg',
				'sku': 'WIDGET-PRO-001',
				'price': '19.99',
				'quantity': '25',
				'warehouse_location': str(address.id),
			},
		)

		self.assertRedirects(response, reverse('inventory'))
		self.assertTrue(Product.objects.filter(sku='WIDGET-PRO-001').exists())
		product = Product.objects.get(sku='WIDGET-PRO-001')
		self.assertEqual(product.seller_id, seller.id)
		self.assertTrue(Inventory.objects.filter(product=product, warehouse_location=address).exists())

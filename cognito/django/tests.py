from __future__ import unicode_literals

from mock import patch, MagicMock
from botocore.exceptions import ClientError
from middleware import APIKeyMiddleware

from django.contrib.auth.models import AnonymousUser, User
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, signals
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import TestCase, TransactionTestCase
from django.test.client import RequestFactory
from django.utils.six import iteritems

from cognito.django.backend import CognitoBackend
from cognito import Cognito

def set_tokens(cls, *args, **kwargs):
    print 'set tokens'
    cls.access_token = 'accesstoken'
    cls.id_token = 'idtoken'
    cls.refresh_token = 'refreshtoken'

def get_user(cls, *args, **kwargs):
    print 'custom get user'
    user = MagicMock(
        user_status=kwargs.pop('user_status', 'CONFIRMED'),
        username=kwargs.pop('access_token', 'testuser'),
        email=kwargs.pop('email', 'test@email.com'),
        given_name=kwargs.pop('given_name', 'FirstName'),
        family_name=kwargs.pop('family_name', 'LastName'),
        UserAttributes = [
        {
            "Name": "sub", 
            "Value": "c7d890f6-eb38-498d-8f85-7a6c4af33d7a"
        }, 
        {
            "Name": "email_verified", 
            "Value": "true"
        }, 
        {
            "Name": "gender", 
            "Value": "male"
        }, 
        {
            "Name": "name", 
            "Value": "FirstName LastName"
        }, 
        {
            "Name": "preferred_username", 
            "Value": "testuser"
        }, 
        {
            "Name": "given_name", 
            "Value": "FirstName"
        }, 
        {
            "Name": "family_name", 
            "Value": "LastName"
        }, 
        {
            "Name": "email", 
            "Value": "test@email.com"
        }
    ]
    )
    user_metadata = {
        'username': user.get('Username'),
        'id_token': cls.id_token,
        'access_token': cls.access_token,
        'refresh_token': cls.refresh_token
    }
    return cls.get_user_obj(username=user.username,
                             attribute_list=user.UserAttributes,
                             metadata=user_metadata)

class AuthTests(TransactionTestCase):
    def set_tokens(cls, *args, **kwargs):
        cls.access_token = 'accesstoken'
        cls.id_token = 'idtoken'
        cls.refresh_token = 'refreshtoken'

    def create_mock_user_obj(self, **kwargs):
        """
        Create a mock UserObj
        :param: kwargs containing desired attrs
        :return: returns mock UserObj
        """
        mock_user_obj = MagicMock(
            user_status=kwargs.pop('user_status', 'CONFIRMED'),
            username=kwargs.pop('access_token', 'testuser'),
            email=kwargs.pop('email', 'test@email.com'),
            given_name=kwargs.pop('given_name', 'FirstName'),
            family_name=kwargs.pop('family_name', 'LastName'),
        )
        for k, v in kwargs.iteritems():
            setattr(mock_user_obj, k, v)

        return mock_user_obj

    def setup_mock_user(self, mock_cognito_user):
        """
        Configure mocked Cognito User
        :param mock_cognito_user: mock Cognito User
        """
        mock_cognito_user.return_value = mock_cognito_user
        self.set_tokens(mock_cognito_user)

        mock_user_obj = self.create_mock_user_obj()
        mock_cognito_user.get_user.return_value = mock_user_obj

    @patch.object(Cognito, 'authenticate')
    @patch.object(Cognito, 'get_user')
    def test_user_authentication(self, mock_get_user, mock_authenticate):
        Cognito.authenticate = set_tokens
        Cognito.get_user = get_user

        user = authenticate(username='testuser',
                            password='password')

        self.assertIsNotNone(user)

    @patch.object(Cognito, 'authenticate')
    def test_user_authentication_wrong_password(self, mock_authenticate):
        Cognito.authenticate.side_effect = ClientError(
            {
                'Error': 
                    {
                        'Message': 'Incorrect username or password.', 'Code': 'NotAuthorizedException'
                    }
            },
            'AdminInitiateAuth')
        user = authenticate(username='username',
                            password='wrongpassword')

        self.assertIsNone(user)


    @patch.object(Cognito, 'authenticate')
    def test_user_authentication_wrong_username(self, mock_authenticate):
        Cognito.authenticate.side_effect = ClientError(
            {
                'Error': 
                    {
                        'Message': 'Incorrect username or password.', 'Code': 'NotAuthorizedException'
                    }
            },
            'AdminInitiateAuth')
        user = authenticate(username='wrongusername',
                            password='password')

        self.assertIsNone(user)

    @patch.object(Cognito, 'authenticate')
    @patch.object(Cognito, 'get_user')
    def test_client_login(self, mock_get_user, mock_authenticate):
        Cognito.authenticate = set_tokens
        Cognito.get_user = get_user

        user = self.client.login(username='testuser',
                                 password='password')
        self.assertTrue(user)

    @patch.object(Cognito, 'authenticate')
    def test_boto_error_raised(self, mock_authenticate):
        """
        Check that any error other than NotAuthorizedException is
        raised as an exception
        """
        Cognito.authenticate.side_effect = ClientError(
            {
                'Error': 
                    {
                        'Message': 'Generic Error Message.', 'Code': 'SomeError'
                    }
            },
            'AdminInitiateAuth')
        with self.assertRaises(ClientError) as error:
            user = authenticate(username='testuser',
                                password='password')
        self.assertEqual(error.exception.response['Error']['Code'], 'SomeError')

    @patch.object(Cognito, 'authenticate')
    @patch.object(Cognito, 'get_user')
    def test_new_user_created(self, mock_get_user, mock_authenticate):
        Cognito.authenticate = set_tokens
        Cognito.get_user = get_user

        User = get_user_model()
        self.assertEqual(User.objects.count(), 0) 

        user = authenticate(username='testuser',
                            password='password')

        self.assertEqual(User.objects.count(), 1) 
        self.assertEqual(user.username, 'testuser')

    @patch.object(Cognito, 'authenticate')
    @patch.object(Cognito, 'get_user')
    def test_existing_user_updated(self, mock_get_user, mock_authenticate):
        Cognito.authenticate = set_tokens
        Cognito.get_user = get_user

        User = get_user_model()
        existing_user = User.objects.create(username='testuser', email='None')
        user = authenticate(username='testuser',
                            password='password')
        self.assertEqual(user.id, existing_user.id)
        self.assertNotEqual(user.email, existing_user.email)
        self.assertEqual(User.objects.count(), 1)

        updated_user = User.objects.get(username='testuser')
        self.assertEqual(updated_user.email, user.email)
        self.assertEqual(updated_user.id, user.id)

    @patch.object(Cognito, 'authenticate')
    @patch.object(Cognito, 'get_user') 
    def test_existing_user_updated_disabled_create_unknown_user(self, mock_get_user, mock_authenticate):
        class AlternateCognitoBackend(CognitoBackend):
            create_unknown_user = False

        Cognito.authenticate = set_tokens
        Cognito.get_user = get_user

        User = get_user_model()
        existing_user = User.objects.create(username='testuser', email='None')

        backend = AlternateCognitoBackend()
        user = backend.authenticate(username='testuser',
                            password='password')
        self.assertEqual(user.id, existing_user.id)
        self.assertNotEqual(user.email, existing_user)
        self.assertEqual(User.objects.count(), 1)

        updated_user = User.objects.get(username='testuser')
        self.assertEqual(updated_user.email, user.email)
        self.assertEqual(updated_user.id, user.id)

    @patch.object(Cognito, 'authenticate')
    @patch.object(Cognito, 'get_user') 
    def test_user_not_found_disabled_create_unknown_user(self, mock_get_user, mock_authenticate):
        class AlternateCognitoBackend(CognitoBackend):
            create_unknown_user = False

        Cognito.authenticate = set_tokens
        Cognito.get_user = get_user

        backend = AlternateCognitoBackend()
        user = backend.authenticate(username='testuser',
                            password='password')

        self.assertIsNone(user)

    def test_add_user_tokens(self):
        User = get_user_model()
        user = User.objects.create(username=settings.COGNITO_TEST_USERNAME)
        user.access_token = 'access_token_value'
        user.id_token = 'id_token_value'
        user.refresh_token = 'refresh_token_value'
        user.backend = 'cognito.django.backend.CognitoBackend'

        request = RequestFactory().get('/login')
        middleware = SessionMiddleware()
        middleware.process_request(request)
        request.session.save()
        signals.user_logged_in.send(sender=user.__class__, request=request, user=user)

        self.assertEqual(request.session['ACCESS_TOKEN'], 'access_token_value')
        self.assertEqual(request.session['ID_TOKEN'], 'id_token_value')
        self.assertEqual(request.session['REFRESH_TOKEN'], 'refresh_token_value')

    def test_model_backend(self):
        """
        Check that the logged in signal plays nice with other backends
        """
        User = get_user_model()
        user = User.objects.create(username=settings.COGNITO_TEST_USERNAME)
        user.backend = 'django.contrib.auth.backends.ModelBackend'

        request = RequestFactory().get('/login')
        middleware = SessionMiddleware()
        middleware.process_request(request)
        request.session.save()
        signals.user_logged_in.send(sender=user.__class__, request=request, user=user)
        

class MiddleWareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_header_missing(self):
        request = self.factory.get('/does/not/matter')

        request.user = AnonymousUser()

        APIKeyMiddleware.process_request(request)

        # Test that missing headers responds properly
        self.assertFalse(hasattr(request, 'api_key'))

    def test_header_transfers(self):
        request = self.factory.get('/does/not/matter', HTTP_AUTHORIZATION_ID='testapikey')

        request.user = AnonymousUser()

        APIKeyMiddleware.process_request(request)

        # Now test with proper headers in place
        self.assertEqual(request.api_key, 'testapikey')

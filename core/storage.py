import json
import mimetypes
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


BLOB_API_URL = 'https://vercel.com/api/blob'
BLOB_API_VERSION = '13'


@deconstructible
class VercelBlobStorage(Storage):
    """Stores uploaded files (product images) in a public Vercel Blob store.

    The blob pathname (e.g. 'product_images/kitten-AbC123.jpeg') is what gets saved
    in the database; url() turns it back into the public blob URL.
    """

    def __init__(self, token=None, base_url=None):
        self.token = token or settings.BLOB_READ_WRITE_TOKEN
        # Read-write tokens look like vercel_blob_rw_<storeId>_<secret>.
        parts = self.token.split('_')
        self.store_id = parts[3] if len(parts) > 3 else ''
        self.base_url = (base_url or settings.BLOB_BASE_URL
                         or f'https://{self.store_id.lower()}.public.blob.vercel-storage.com')

    def _request(self, method, path, data=None, headers=None):
        request = urllib.request.Request(
            f'{BLOB_API_URL}{path}',
            data=data,
            method=method,
            headers={
                'authorization': f'Bearer {self.token}',
                'x-api-version': BLOB_API_VERSION,
                'x-vercel-blob-store-id': self.store_id,
                **(headers or {}),
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))

    def _save(self, name, content):
        name = name.replace('\\', '/')
        content_type = (getattr(content, 'content_type', None)
                        or mimetypes.guess_type(name)[0]
                        or 'application/octet-stream')
        content.seek(0)
        result = self._request(
            'PUT',
            '/?' + urllib.parse.urlencode({'pathname': name}),
            data=content.read(),
            headers={
                'x-vercel-blob-access': 'public',
                'x-content-type': content_type,
                'x-add-random-suffix': '1',
            },
        )
        return result['pathname']

    def _open(self, name, mode='rb'):
        raise NotImplementedError('Reading blobs back through Django storage is not supported.')

    def delete(self, name):
        if not name:
            return
        self._request(
            'POST',
            '/delete',
            data=json.dumps({'urls': [self.url(name)]}).encode('utf-8'),
            headers={'content-type': 'application/json'},
        )

    def exists(self, name):
        # Uploads get a random suffix, so names never collide.
        return False

    def url(self, name):
        return f'{self.base_url}/{urllib.parse.quote(name)}'

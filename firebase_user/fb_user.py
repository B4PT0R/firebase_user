import requests
import json
from objdict_bf import objdict
import time
import os
import urllib
from datetime import datetime
import mimetypes

def list_files(directory):
    """
    List all file paths, relative to the given directory, in the directory and its subdirectories,
    along with details like size, MIME type, and last modified time in ISO 8601 format.

    :param directory: The root directory to walk through.
    :return: A dict with relative paths as keys and file details as values.
    """
    file_details = {}
    for root, dirs, files in os.walk(directory):
        for file in files:
            # Get the full path
            full_path = os.path.join(root, file)
            # Convert to relative path
            relative_path = os.path.relpath(full_path, directory)
            # Get file details
            stat_info = os.stat(full_path)
            mime_type, _ = mimetypes.guess_type(full_path)
            updated_time = datetime.utcfromtimestamp(stat_info.st_mtime).isoformat() + 'Z'  # ISO 8601 format
            file_details[relative_path] = {
                'size': stat_info.st_size,
                'type': mime_type if mime_type else 'Unknown',
                'updated': updated_time
            }
    
    return file_details

def is_newer(file1, file2):
    """
    Compare the 'updated' timestamp of two files to determine if file1 is newer than file2.

    :param file1: Details of the first file.
    :param file2: Details of the second file.
    :return: True if file1 is newer than file2, False otherwise.
    """
    # Parse the 'updated' timestamps into datetime objects
    file1_updated = datetime.fromisoformat(file1['updated'].rstrip('Z'))
    file2_updated = datetime.fromisoformat(file2['updated'].rstrip('Z'))

    # Compare the datetime objects
    return file1_updated > file2_updated

def convert_in(value):
    if isinstance(value, str):
        return {'stringValue': value}
    elif isinstance(value, bool):
        return {'booleanValue': value}
    elif isinstance(value, int):
        return {'integerValue': value}
    elif isinstance(value, float):
        return {'doubleValue': value}
    elif isinstance(value, dict):
        return {'mapValue': {'fields': {k: convert_in(v) for k, v in value.items()}}}
    elif isinstance(value, list):
        return {'arrayValue': {'values': [convert_in(v) for v in value]}}
    else:
        return {'nullValue': None}

def to_typed_dict(data):
    return {'fields': {k: convert_in(v) for k, v in data.items()}}

def convert_out(value):
    if 'nullValue' in value:
        return None
    elif 'stringValue' in value:
        return value['stringValue']
    elif 'booleanValue' in value:
        return value['booleanValue']
    elif 'integerValue' in value:
        return int(value['integerValue'])
    elif 'doubleValue' in value:
        return float(value['doubleValue'])
    elif 'timestampValue' in value:
        return value['timestampValue']  # Or convert to a Python datetime object
    elif 'geoPointValue' in value:
        return value['geoPointValue']  # Returns a dict with 'latitude' and 'longitude'
    elif 'referenceValue' in value:
        return value['referenceValue']  # Firestore document reference
    elif 'mapValue' in value:
        content=value['mapValue']['fields']
        return {key: convert_out(value) for key, value in content.items()}
    elif 'arrayValue' in value:
        content=value['arrayValue'].get('values', [])
        return [convert_out(item) for item in content]
    else:
        return None  # Add additional cases as needed

def to_dict(document):
    """
    Convert a Firestore document with type annotations to a regular dictionary.
    """
    if 'fields' in document:
        return {key: convert_out(value) for key, value in document['fields'].items()}
    else:
        return {}

class Auth:

    FIREBASE_REST_API = "https://identitytoolkit.googleapis.com/v1/accounts"

    def __init__(self, client):
        self.client=client


    def sign_in(self, email, password):
        """
        Authenticate a user using email and password.
        Returns a dictionary with idToken and refreshToken.
        """
        url = f"{self.FIREBASE_REST_API}:signInWithPassword?key={self.client.config.apiKey}"
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({"email": email, "password": password, "returnSecureToken": True})
        
        response = self.client._make_request(type='post',url=url, headers=headers, data=data)
        self.client.user=objdict(response.json())
        if self.client.verbose:
            print("User successfuly authenticated.")
        return self.client.user

    def refresh_token(self):
        """
        Refresh the user's idToken using the refreshToken.
        """
        url = f"https://securetoken.googleapis.com/v1/token?key={self.client.config.apiKey}"
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({"grant_type": "refresh_token", "refresh_token": self.client.user.refreshToken})
        
        response = self.client._make_request(type='post',url=url, headers=headers, data=data)
        refresh=objdict(response.json())
        self.client.user.idToken=refresh.id_token
        self.client.user.refreshToken=refresh.refresh_token
        self.client.user.expiresIn=refresh.expires_in
        if self.client.verbose:
            print("Token successfuly refreshed.")

    def log_out(self):
        self.client.user=None
        if self.client.verbose:
            print("User successfuly logged out.")
    
    def sign_up(self, email, password):
        """
        Create a new user with email and password.
        Returns a user object with idToken and refreshToken.
        """
        url = f"{self.FIREBASE_REST_API}:signUp?key={self.client.config.apiKey}"
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({"email": email, "password": password, "returnSecureToken": True})
        
        response = self.client._make_request(type='post',url=url, headers=headers, data=data)
        self.client.user=objdict(response.json())
        if self.client.verbose:
            print(f"New user successfuly created: {self.client.user.email}")


    def change_password(self, new_password):
        """
        Update the password of a user.
        """
        url = f"{self.FIREBASE_REST_API}:update?key={self.client.config.apiKey}"
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({"idToken": self.client.user.idToken, "password": new_password, "returnSecureToken": True})
        
        response = self.client._make_request(type='post',url=url, headers=headers, data=data)
        self.client.user=objdict(response.json())
        if self.client.verbose:
            print("Password changed.")

class Firestore:

    def __init__(self, client):
        self.client=client
        self.base_url = f"https://firestore.googleapis.com/v1/projects/{self.client.config.projectId}/databases/(default)/documents"
        self.stop_listener=False

    def get_document(self):
        url = f"{self.base_url}/users/{self.client.user.email}"
        headers = {'Authorization': "Bearer {token}"}
        response = self.client._request(type='get',url=url, headers=headers)
        if response.status_code != 200:
            resp=objdict(response.json())
            if self.client.user.get("idToken") and resp.error.status=='UNAUTHENTICATED':
                self.client.auth.refresh_token()
                response = self.client._request(type='get',url=url, headers=headers)
                if response.status_code != 200:
                    if resp.error.status=='NOT_FOUND':
                        return objdict()
                    else:
                        print("Error response:", response.text)
                        response.raise_for_status()
            elif resp.error.status=='NOT_FOUND':
                return objdict()    
            else:
                print("Error response:", response.text)
                response.raise_for_status()
        if self.client.verbose:
            print("Document successfuly fetched from firestore.")
        return objdict(to_dict(response.json()))

    def set_document(self, data):
        url = f"{self.base_url}/users/{self.client.user.email}"
        headers = {'Authorization': "Bearer {token}", 'Content-Type': 'application/json'}
        formatted_data = to_typed_dict(data)
        response = self.client._make_request(type='patch',url=url, headers=headers, json=formatted_data)
        if self.client.verbose:
            print("Document successfuly set in firestore.")

    def start_listener(self, interval=3):
        """
        Lance une boucle d'écoute pour détecter un changement du document Firestore.
        """
        last_data = self.get_document()
        if self.client.verbose:
            print("Now listening for changes in the document...")
        while True:
            time.sleep(interval)
            current_data = self.get_document()
            if current_data != last_data:
                if self.client.verbose:
                    print("Change detected.")
                break
        if self.client.verbose:
            print("Finished listening. Returning the updated document.")
        return current_data
   
class Storage:
    def __init__(self, client):
        self.client=client
        self.base_url = f"https://firebasestorage.googleapis.com/v0/b/{self.client.config.storageBucket}/o/"

    def encode_path(self, path):
        """
        URL-encode the path.
        """
        return urllib.parse.quote(path, safe='')

    def list_files(self):
        """
        List files in the user's storage directory with additional metadata.
        """
        user_folder = f"{self.client.user.email}/"
        encoded_path = self.encode_path(user_folder)
        request_url = self.base_url + "?prefix=" + encoded_path

        headers = {'Authorization': "Bearer {token}"}
        response = self.client._make_request(type='get',url=request_url, headers=headers)

        files = {}
        for item in response.json().get('items', []):
            # Construct URL for getting detailed metadata
            detail_url = self.base_url + self.encode_path(item['name']) + "?alt=json"
            detail_response = self.client._make_request(type='get',url=detail_url, headers=headers)
            file_metadata = detail_response.json()
            name=file_metadata['name'].removeprefix(self.client.user.email+'/')
            files[name]={
                'size': file_metadata.get('size', 'Unknown'),
                'type': file_metadata.get('contentType', 'Unknown'),
                'updated': file_metadata.get('updated', 'Unknown')
            }
        return files

        
    
    def delete_file(self, file_name):
        """
        Delete a file from Firebase Storage.
        """
        encoded_path = self.encode_path(f"{self.client.user.email}/{file_name}")
        request_url = self.base_url + encoded_path
        headers = {'Authorization': "Bearer {token}"}
        response = requests.delete(request_url, headers=headers)
        if response.status_code != 200:
            print("Error response:", response.text)
            response.raise_for_status()
        if self.client.verbose:
            print(f"Successfuly deleted {file_name}")

    def download_file(self, remote_path, local_path):
        """
        Download a file from Firebase Storage.
        """
        encoded_path = self.encode_path(f"{self.client.user.email}/{remote_path}")
        request_url = self.base_url + encoded_path + "?alt=media"
        headers = {'Authorization': "Bearer {token}"}
        response = self.client._make_request(type='get',url=request_url, headers=headers, stream=True)
        abs_path=os.path.abspath(local_path)
        dir_name=os.path.dirname(abs_path)
        if not os.path.isdir(dir_name):
            os.makedirs(dir_name)
        with open(abs_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        if self.client.verbose:
            print(f"Successfuly downloaded user_storage/{remote_path} to {abs_path}")

    def upload_file(self, local_path, remote_path):
        """
        Upload a file to Firebase Storage.
        """
        encoded_path = self.encode_path(f"{self.client.user.email}/{remote_path}")
        request_url = self.base_url + encoded_path
        headers = {'Authorization': "Bearer {token}"}
        with open(local_path, 'rb') as f:
            files = {'file': f}
            response = self.client._make_request(type='post',url=request_url, headers=headers, files=files)
        abs_path=os.path.abspath(local_path)
        if self.client.verbose:
            print(f"Successfuly uploaded {abs_path} to user_storage/{remote_path}")
    
    def dump_folder(self, local_folder):
        """
        Synchronizes the local folder to Firebase Storage.
        - Uploads newer files to Storage.
        - Deletes files from Storage that don't exist locally.
        """
        if not os.path.isdir(local_folder):
            raise FileExistsError(f"Cannot dump a folder if it does not exist: {local_folder}")
        
        local_folder=os.path.abspath(local_folder)
        lfiles = list_files(local_folder)
        sfiles = self.list_files()

        #Handle uploads
        for file in lfiles:
            if file not in sfiles or (file in sfiles and is_newer(lfiles[file],sfiles[file])):
                self.upload_file(os.path.join(local_folder,file),file)

        # Handle deletions
        for file in sfiles:
            if not file in lfiles:
                self.delete_file(file)

    
    def load_folder(self, local_folder):
        """
        Synchronizes Firebase Storage to the local folder.
        - Downloads newer files from Storage.
        - Deletes local files that don't exist in Storage.
        (Beware that this will overwrite/delete files in the chosen local folder, use with caution.)
        """
        local_folder=os.path.abspath(local_folder)
        lfiles = list_files(local_folder)
        sfiles = self.list_files()

        #Handle downloads
        for file in sfiles:
            if file not in lfiles or (file in lfiles and is_newer(sfiles[file],lfiles[file])):
                self.download_file(file,os.path.join(local_folder,file))

        # Handle deletions
        for file in lfiles:
            local_file=os.path.abspath(os.path.join(local_folder,file))
            if not file in sfiles:
                os.remove(local_file)
                if self.client.verbose:
                    print(f"Deleted {local_file}")
                parent=os.path.dirname(local_file)
                while not os.listdir(parent) and local_folder in parent:
                    os.rmdir(parent)
                    if self.client.verbose:
                        print(f"Deleted {parent}")
                    parent=os.path.dirname(parent)

    
class FirebaseClient:

    def __init__(self, config,verbose=False):
        self.config = objdict(config)
        self.auth = Auth(self)
        self.firestore = Firestore(self)
        self.storage = Storage(self)
        self.user=None
        self.verbose=verbose

    def _request(self,type,**kwargs):
        if kwargs.get('headers'):
            kwargs['headers']=self._format_headers(kwargs['headers'])
        if type=='post':
            response = requests.post(**kwargs)
        elif type=='get':
            response = requests.get(**kwargs)
        elif type=='delete':
            response = requests.delete(**kwargs)
        elif type=='patch':
            response = requests.patch(**kwargs)
        else:
            raise ValueError(f"Unsupported request type: {type}")
        
        return response
    
    @property
    def authenticated(self):
        return self.user and self.user.get('idToken')
        
    def _make_request(self,type,**kwargs):
        response=self._request(type,**kwargs)
        if response.status_code != 200:
            resp=objdict(response.json())
            if self.user.get("idToken") and resp.error.status=='UNAUTHENTICATED':
                self.auth.refresh_token()
                response=self._request(type,**kwargs)
                if response.status_code != 200:
                    print("Error response:", response.text)
                    response.raise_for_status()    
            else:
                print("Error response:", response.text)
                response.raise_for_status()
        return response
    
    def _format_headers(self,headers):
        formatted=headers.copy()
        if formatted.get('Authorization') and self.user:
            formatted['Authorization']=formatted['Authorization'].format(token=self.user.idToken)
        return formatted

import requests
from requests import HTTPError
import json
from objdict_bf import objdict
import time
import os
import urllib
from datetime import datetime
import mimetypes
from threading import Thread
from queue import Queue

def convert_path_to_prefix(path):
    return path.replace('\\','/')

def convert_prefix_to_path(prefix):
    elements=prefix.split('/')
    return os.path.join(*elements)

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
    file1_size=file1['size']
    file2_updated = datetime.fromisoformat(file2['updated'].rstrip('Z'))
    file2_size=file2['size']
    # Compare the datetime objects as well as size
    return file1_updated > file2_updated and file1_size != file2_size

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

class FirebaseException(Exception):
    def __init__(self,message,*args):
        super().__init__(self,message,*args)
        self.message=message

    def __str__(self):
        return f"Error: {self.message}"


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
    
    def sign_in_with_user_object(self,user):
        if user and user.get('idToken') and user.get('refreshToken') and user.get('email') and self.is_valid(user.idToken):
            self.client.user=user 
            if self.client.verbose:
                print("Successfuly signed in with user object.")
        else:
            raise ValueError("Invalid or expired user idToken.")
        
    def is_valid(self,idToken=None):
        """
        Check if the given idToken is still valid.
        """
        user_token=self.client.user.get('idToken') if self.client.user is not None else None
        idToken=idToken or user_token

        # Firebase endpoint for verifying the idToken
        verify_token_url = f"{self.FIREBASE_REST_API}:lookup?key={self.client.config.apiKey}"
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({"idToken": idToken})

        response = self.client._request(type='post', url=verify_token_url, headers=headers, data=data)
        
        # If the token is valid, Firebase will return the user details
        # If the token is invalid, Firebase will return an error
        if response.status_code == 200:
            return True
        else:
            return False

    @property
    def authenticated(self):
        return self.client.user is not None and self.client.user.get('idToken') is not None and self.client.user.get('refreshToken') is not None and self.client.user.get('email') is not None and self.is_valid()


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

    def delete_user(self):
        """
        Deletes the authenticated user from Firebase Authentication.
        """
        # Endpoint for deleting a user account in Firebase
        url = f"{self.FIREBASE_REST_API}:delete?key={self.client.config.apiKey}"
        headers = {"content-type": "application/json; charset=UTF-8"}
        data = json.dumps({"idToken": self.client.user.idToken})
        
        response = self.client._make_request(type='post', url=url, headers=headers, data=data)

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

    class Listener:

        def __init__(self,client,collection,document,interval=3,timeout=None,callback=None):
            self.client=client
            self.interval=interval
            self.timeout=timeout
            self.callback=callback
            self.collection=collection
            self.document=document
            self.base_url = f"https://firestore.googleapis.com/v1/projects/{self.client.config.projectId}/databases/(default)/documents"
            self.stop_listening=False
            self.listener=None
            self.queue=None

        def listen(self):
            """
            Start a listening loop to wait for a change in a given firestore document.
            Will make a read request every <interval> seconds until a change is detected or <timeout> is reached (3600 seconds by default)
            Returns the updated document.
            """
            self.stop_listening=False
            last_data = self.client.firestore.get_document(self.collection,self.document)
            if self.client.verbose:
                print("Now listening for changes in the document...")
            timeout=self.timeout or 3600
            timer=0
            while timer<timeout and not self.stop_listening:
                time.sleep(self.interval)
                timer+=self.interval
                current_data = self.client.firestore.get_document(self.collection,self.document)
                if current_data != last_data:
                    if self.client.verbose:
                        print("Change detected.")
                    if self.callback:
                        self.callback(current_data)
                    self.queue.put(current_data)
                    last_data=current_data
            self.queue.put("<STOPPED>")
            self.stop_listening=False
            if self.client.verbose:
                print("Finished listening.")
        
        def start(self):
            self.queue=Queue()
            self.listener=Thread(target=self.listen)
            self.listener.start()

        def stop(self):
            self.stop_listening=True
            if self.listener is not None:
                self.listener.join()
                self.listener=None

        def get_data(self):
            data=self.queue.get()
            return data

        @property
        def is_listening(self):
            return self.listener is not None and not self.stop_listening


    def __init__(self, client):
        self.client=client
        self.base_url = f"https://firestore.googleapis.com/v1/projects/{self.client.config.projectId}/databases/(default)/documents"
        self.stop_listening=False
        self.is_listening=True

    def get_user_data(self):
        return self.get_document('users',self.client.user.email)

    def get_document(self,collection,document):
        url = f"{self.base_url}/{collection}/{document}"
        headers = {'Authorization': "Bearer {token}"}
        response = self.client._make_request(type='get',url=url, headers=headers,default=lambda :"NOT_FOUND")
        if response=="NOT_FOUND":
            output=objdict()
        else:
            output=objdict(to_dict(response.json()))
        if self.client.verbose:
            print("Document successfuly fetched from firestore.")
        return output
    
    def set_user_data(self, data):
        return self.set_document('users',self.client.user.email,data)

    def set_document(self,collection,document, data):
        url = f"{self.base_url}/{collection}/{document}"
        headers = {'Authorization': "Bearer {token}", 'Content-Type': 'application/json'}
        formatted_data = to_typed_dict(data)
        response = self.client._make_request(type='patch',url=url, headers=headers, json=formatted_data)
        if self.client.verbose:
            print("Document successfuly set in firestore.")

    def delete_document(self, collection, document):
        url = f"{self.base_url}/{collection}/{document}"
        headers = {'Authorization': "Bearer {token}"}
        response = self.client._make_request(type='delete', url=url, headers=headers)
        if self.client.verbose:
            print("Document successfuly deleted.")

    def listener(self,collection,document,interval=3,timeout=None,callback=None):
        return Firestore.Listener(self.client,collection,document,interval=interval,timeout=timeout,callback=callback)



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
            relative_prefix=file_metadata['name'].removeprefix(self.client.user.email+'/')
            name=convert_prefix_to_path(relative_prefix)
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
        response = self.client._make_request(type='delete',url=request_url, headers=headers)
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
                self.upload_file(os.path.join(local_folder,file),convert_path_to_prefix(file))

        # Handle deletions
        for file in sfiles:
            if not file in lfiles:
                self.delete_file(convert_path_to_prefix(file))

    
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
                self.download_file(convert_path_to_prefix(file),os.path.join(local_folder,file))

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
        
    def _make_request(self,type,default=None,**kwargs):
        response=self._request(type,**kwargs)
        if response.status_code >= 400:
            try:
                error=objdict(response.json()['error'],_use_default=True)
            except:
                error=objdict(_use_default=True)
            if self.user is not None and self.user.get("idToken") and error.status=='UNAUTHENTICATED':
                self.auth.refresh_token()
                response=self._request(type,**kwargs)
                if response.status_code >= 400:
                    try:
                        error=objdict(response.json()['error'],_use_default=True)
                    except:
                        error=objdict(_use_default=True)
                    if error.status=='NOT_FOUND':
                        if default:
                            return default()
                        else:
                            raise FirebaseException("NOT_FOUND")
                    else:
                        msg=error.status or error.message or "Unknown Firebase error"
                        raise FirebaseException(msg)
            elif error.status=='NOT_FOUND':
                if default:
                    return default()
                else:
                    raise FirebaseException('NOT_FOUND')
            else:
                msg=error.status or error.message or "Unknown Firebase error"
                raise FirebaseException(msg)
        return response
    
    def _format_headers(self,headers):
        formatted=headers.copy()
        if formatted.get('Authorization') and self.user:
            formatted['Authorization']=formatted['Authorization'].format(token=self.user.idToken)
        return formatted

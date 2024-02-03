
# firebase_user

This package is meant as a convenient client interface for the firebase REST API.
It doesn't use the firebase-admin sdk and doesn't require any admin credentials.
Only uses the firebase app config object of your app which can safely be exposed in the client codebase.
Supports Auth, Firestore and Storage for a quick yet powerful decentralized user management on the client side.

You need to setup a firebase project via the firebase console in order to use it.
Don't forget to set up proper security rules in firebase to prevent a user getting access to other users' data content. 

## Installation

```bash
$ pip install firebase-user
```

## Usage

```python
from firebase_user import FirebaseClient
import json

#Get the json app config of your project
with open('app_config.json','r') as f:
    config=json.load(f)

#Initialize the client with it
client=FirebaseClient(config)

#----------------Authentication-----------------

#Sign up for a new account
client.auth.sign_up("email","password")
#or sign in
client.auth.sign_in("email","password")

#Check authentication success
print(client.auth.authenticated)
# True

#Additional auth features
client.auth.change_password("new_password")
client.auth.refresh_token() #This method is called automatically in case the initial token expired
client.auth.delete_user()

#---------------- Firestore -----------------

#Get the user's data from firestore (ie. the document with user's email adress as name in the 'users' collection) 
data=client.firestore.get_user_data()

#Make changes (nested attribute-style access supported)
data.age=34
data.hobbies=["Guitar playing","Basketball"]

#Dump changes to firestore
client.firestore.set_user_data(data)

#You may also read and write to a chosen document in a given collection (provided the user has permission to access it)
data=client.firestore.get_document(collection,document)
client.firestore.set_document(collection,document,data)

#Using a firestore listener thread to detect changes in a document (optional callback called when a change is detected)
def callback(document):
    print(f"Document changed: {document}")

listener=client.firestore.listener(collection,document,interval=1,timeout=3600,callback=callback)
listener.start() # start the listening thread
print(listener.is_listening) #True
data=listener.get_data() # waits until a change is detected and captures it
listener.stop() #stop listening

#----------------- Storage ------------------

#list files in the user's storage (includes files metadata)
files=client.storage.list_files()

#upload / download a file from / to cloud storage
client.storage.upload_file(local_file="./folder/file.txt",remote_file="folder/file.txt")
client.storage.download_file(remote_file="folder/file.txt",local_file="./folder/file.txt")

#load / dump a whole folder from / to the cloud storage (will overwrite the local / remote folder as a whole)
client.storage.load_folder("./folder")
client.storage.dump_folder("./folder")

#log out
client.auth.log_out()
print(client.auth.authenticated)
# False

```

## License

This project is available under MIT license. Please see the LICENSE file for more details.

## Contributions

Contributions are welcome. Please open an issue or a pull request to suggest changes or additions.

## Contact

For any questions or support requests, please contact Baptiste Ferrand at the following address: bferrand.maths@gmail.com.

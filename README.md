
# firebase_user

This package is meant as a convenient client interface for the firebase REST API.
It doesn't use the firebase-admin sdk and doesn't require any admin credentials.
Only uses the firebase app config object which can safely be exposed in the client codebase.
Supports Auth, Firestore and Storage for a quick yet powerful decentralized user management on the client side.


## Installation

```bash
$ pip install firebase-user
```

## Usage

Minimal setting:

```python
from firebase_user import Client
import json

with open('app_config.json','r') as f:
    config=json.load(f)

client=Client(config)

client.auth.sign_up("email","password")
#or
client.auth.sign_in("email","password")

print(client.authenticated)
# True

client.auth.change_password("new_password")

data=client.firebase.get_document()

data.age=34
data.hobbies=["Guitar playing","Basketball"]

client.firebase.set_document(data)

files=client.storage.list_files()

client.storage.upload_file(local_file="./folder/file.txt",remote_file="folder/file.txt")
client.storage.download_file(remote_file="folder/file.txt",remote_file="./folder/file.txt")

client.storage.load_folder("./folder")
client.storage.dump_folder("./folder")

client.auth.log_out()
print(client.authenticated)
# False

```

## License

This project is available under MIT license. Please see the LICENSE file for more details.

## Contributions

Contributions are welcome. Please open an issue or a pull request to suggest changes or additions.

## Contact

For any questions or support requests, please contact Baptiste Ferrand at the following address: bferrand.maths@gmail.com.

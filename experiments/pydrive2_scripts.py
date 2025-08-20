from pydrive2.drive import GoogleDrive
from pydrive2.auth import GoogleAuth

gauth = GoogleAuth()
gauth.LocalWebserverAuth()  # Creates local webserver and auto handles authentication.
drive = GoogleDrive(gauth)

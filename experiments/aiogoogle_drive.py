import webbrowser

import yaml
from aiogoogle.auth.creds import ClientCreds
from aiogoogle.auth.utils import create_secret
from aiogoogle.client import Aiogoogle
from aiohttp import web
from aiohttp.web import Application, HTTPFound, RouteTableDef, json_response, run_app

with open("keys.yaml", "r") as stream:
    config = yaml.load(stream, Loader=yaml.FullLoader)

EMAIL = config["user_creds"]["email"]
CLIENT_CREDS = ClientCreds(
    client_id=config["client_creds"]["client_id"],
    client_secret=config["client_creds"]["client_secret"],
    scopes=config["client_creds"]["scopes"],
    redirect_uri="http://localhost:5000/callback/aiogoogle",
)
state = create_secret()  # Shouldn't be a global hardcoded variable.


LOCAL_ADDRESS = "localhost"
LOCAL_PORT = 5000

routes = RouteTableDef()
aiogoogle = Aiogoogle(client_creds=CLIENT_CREDS)

# ----------------------------------------#
#                                         #
# **Step A (Check OAuth2 figure above)**  #
#                                         #
# ----------------------------------------#


@routes.get("/authorize")
async def authorize(request: web.Request) -> web.Response:
    if aiogoogle.oauth2.is_ready(CLIENT_CREDS):
        uri = aiogoogle.oauth2.authorization_url(
            client_creds=CLIENT_CREDS,
            state=state,
            access_type="offline",
            include_granted_scopes=True,
            login_hint=EMAIL,
            prompt="select_account",
        )
        # Step A
        raise HTTPFound(uri)
    else:
        return web.Response(
            text="Client doesn't have enough info for Oauth2", status=500
        )


# ----------------------------------------------#
#                                              #
# **Step B (Check OAuth2 figure above)**       #
#                                              #
# ----------------------------------------------#
# NOTE:                                        #
#  you should now be authorizing your app @    #
#   https://accounts.google.com/o/oauth2/      #
# ----------------------------------------------#

# ----------------------------------------------#
#                                              #
# **Step C, D & E (Check OAuth2 figure above)**#
#                                              #
# ----------------------------------------------#


# Step C
# Google should redirect current_user to
# this endpoint with a grant code
@routes.get("/callback/aiogoogle")
async def callback(request):
    if request.query.get("error"):
        error = {
            "error": request.query.get("error"),
            "error_description": request.query.get("error_description"),
        }
        return json_response(error)
    elif request.query.get("code"):
        returned_state = request.query["state"]
        # Check state
        if returned_state != state:
            return web.Response(text="NO", status=500)
        # Step D & E (D send grant code, E receive token info)
        full_user_creds = await aiogoogle.oauth2.build_user_creds(
            grant=request.query.get("code"), client_creds=CLIENT_CREDS
        )
        return json_response(full_user_creds)
    else:
        # Should either receive a code or an error
        return web.Response(
            text="Something's probably wrong with your callback", status=400
        )


if __name__ == "__main__":
    app = Application()
    app.add_routes(routes)

    webbrowser.open("http://" + LOCAL_ADDRESS + ":" + str(LOCAL_PORT) + "/authorize")
    run_app(app, host=LOCAL_ADDRESS, port=LOCAL_PORT)

from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token

app_name = "core"

urlpatterns = [
    # POST username/password -> {"token": "..."}
    path("auth/token/", obtain_auth_token, name="auth-token"),
]

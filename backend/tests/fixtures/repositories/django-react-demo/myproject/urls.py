from django.urls import path


def users_view(request):
    pass

urlpatterns = [
    path("api/v1/users/", users_view),
]

"""
URL configuration for line_bot_backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path

# Import 'views' from the 'line_bot' app
from line_bot import views as line_views

urlpatterns = [
    path('admin/', admin.site.urls),

    # URL for the Webhook Endpoint
    # This is the "gate" where the LINE Server will send a 'POST' request.
    # 'callback/': is the URL (e.g., https://your-domain.com/callback/)
    # line_views.callback: is the 'callback' function in 'line_bot/views.py' that will be called
    path('callback/', line_views.callback, name='callback'),
]

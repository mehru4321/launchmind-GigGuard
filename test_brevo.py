# import os
# from dotenv import load_dotenv
# # from brevo import Brevo
# # from brevo.transactional_emails import SendTransacEmailRequestSender, SendTransacEmailRequestToItem

# load_dotenv()

# # Get token
# BREVO_API_KEY = os.getenv("BREVO_API_KEY")

# client = Brevo(
#     api_key=BREVO_API_KEY,
# )

# client.transactional_emails.send_transac_email(
#     html_content="<html><head></head><body><p>Hello,</p>This is my first transactional email sent from Brevo.</p></body></html>",
#     sender=SendTransacEmailRequestSender(
#         email="mehrunisanasir@gmail.com",
#         name="mehru from GigGuard",
#     ),
#     subject="Hello from Brevo!",
#     to=[
#         SendTransacEmailRequestToItem(
#             email="mehrunisanasir1@gmail.com",
#             name="receiver",
#         )
#     ],
# )
import os
from dotenv import load_dotenv
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

load_dotenv()

BREVO_API_KEY = os.getenv("BREVO_API_KEY")

configuration = sib_api_v3_sdk.Configuration()
configuration.api_key['api-key'] = BREVO_API_KEY

api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))

send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
    html_content="<html><head></head><body><p>Hello,</p>This is my first transactional email sent from Brevo.</p></body></html>",
    sender={"email": "mehrunisanasir@gmail.com", "name": "mehru from GigGuard"},
    subject="Hello from Brevo!",
    to=[{"email": "mehrunisanasir1@gmail.com", "name": "receiver"}]
)

try:
    response = api_instance.send_transac_email(send_smtp_email)
    print("Email sent! Message ID:", response.message_id)
except ApiException as e:
    print("Error:", e)
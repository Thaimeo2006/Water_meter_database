"""Define UI of admin page"""

from database import User, Customer, Meter, MeterRecord
from sqladmin import ModelView
from wtforms import Form, StringField, PasswordField, FloatField
from wtforms.validators import DataRequired, Optional, Regexp, Length
from password_store import pwd_context
from markupsafe import Markup

class UserForm(Form):

    username = StringField(
        "Username",
        validators=[
            DataRequired()
        ]
    )

    password = PasswordField(
        "New password",
        validators=[
            Optional(),
            Length(
                min=12,
                message="Password must be at least 12 characters."
            ),
            Regexp(
                r'^[\x21-\x7E]+$',
                message="Password contains invalid characters."
            )
        ]
    )

class MeterForm(Form):
    customer_id = StringField(
        "Customer Identity Number (CCCD)",
        validators=[DataRequired()]
    )
    address = StringField(
        "Address",
        validators=[DataRequired()]
    )
    latitude = FloatField(
        "Latitude",
        validators=[DataRequired()]
    )
    longitude = FloatField(
        "Longitude",
        validators=[DataRequired()]
    )

class UserAdmin(ModelView, model=User):
    column_list = [User.id, User.username]
    column_searchable_list = [User.username]
    name = "Employee" 
    name_plural = "Employee list"
    icon = "fa-solid fa-user"

    column_details_list = [
        User.username,
        User.password_hash
    ]

    form = UserForm

    form_columns = [User.username, "password"]

    async def on_model_change(self, data, model, is_created, request):
        plain_password = data.pop("password", None)

        if is_created and not plain_password:
            raise ValueError("Password is required when creating a new employee!")

        if plain_password:
            data["password_hash"] = pwd_context.hash(plain_password)

class CustomerAdmin(ModelView, model=Customer):
    column_list = [Customer.name, Customer.identity_number, Customer.address]
    column_default_sort = [(Customer.identity_number, False)]
    column_searchable_list = [Customer.name, Customer.identity_number]
    name = "Customer"
    name_plural = "Customer list"
    icon = "fa-solid fa-house"

    column_sortable_list = [
        Customer.identity_number,
        Customer.address
    ]
    column_details_list = [
        Customer.name, 
        Customer.identity_number, 
        Customer.address,
        Customer.meters
    ]

    form_include_pk = True
    form_columns = [
        Customer.identity_number,
        Customer.name, 
        Customer.address
    ]

class MeterAdmin(ModelView, model=Meter):
    column_list = [Meter.id, Meter.owner, Meter.address]
    column_searchable_list = [Meter.address]
    name = "Meter"
    name_plural = "Meter list"
    icon = "fa-solid fa-gauge-high"

    column_details_list = [
        Meter.id,
        Meter.address,
        Meter.latitude,
        Meter.longitude,
        Meter.last_paid_record,
    ]

    form = MeterForm

class MeterRecordAdmin(ModelView, model=MeterRecord):
    column_list = [
        MeterRecord.id,
        MeterRecord.meter_id,
        MeterRecord.photographer_id,
        MeterRecord.result,
        MeterRecord.record_time
    ]
    column_default_sort = [(MeterRecord.record_time, True)]
    column_details_list = [
        MeterRecord.meter,
        MeterRecord.image_path,
        MeterRecord.result, 
        MeterRecord.record_time,
        MeterRecord.photographer,
        MeterRecord.coordinates_path,
        MeterRecord.ability
    ]
    column_labels = {
        MeterRecord.image_path: "image",
        MeterRecord.coordinates_path: "coordinates"
    }
    column_formatters_detail = {
        MeterRecord.image_path: lambda model, attribute: Markup(
            f'<a href="/{model.image_path}" target="_blank">'
            f'<img src="/{model.image_path}" style="max-height: 300px; border-radius: 8px; border: 1px solid #ccc; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">'
            f'</a>'
        ) if model.image_path else "",
        
        MeterRecord.coordinates_path: lambda model, attribute: Markup(
            f'<a href="/{model.coordinates_path}" target="_blank" style="padding: 8px 16px; background-color: #0d6efd; color: white; text-decoration: none; border-radius: 4px; display: inline-block;">'
            f'<i class="fa-solid fa-file-lines"></i> See .txt file'
            f'</a>'
        ) if model.coordinates_path else ""
    }
    column_sortable_list = [MeterRecord.record_time, MeterRecord.result]
    column_default_sort = ("record_time", True) 
    name = "Meter record"
    name_plural = "Meter record list"
    icon = "fa-solid fa-droplet"
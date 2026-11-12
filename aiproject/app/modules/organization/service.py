from app.core.exceptions import BusinessError
from app.core.security.authorization import require_permission
from .repository import OrganizationRepository


def organizations(keyword, limit, db, p):
    return OrganizationRepository(db).list_organizations(keyword, limit)


def colleagues(name, db, p):
    return OrganizationRepository(db).find_colleagues(name)


def colleague_contact(employee_id, db, p):
    require_permission(p, "directory:contacts")
    user = OrganizationRepository(db).get_employee(employee_id)
    if not user or user.user_type != "employee" or user.status != "normal":
        raise BusinessError(404, "员工不存在")
    return {"id": user.id, "real_name": user.real_name, "department": user.department, "contact_info": user.contact_info}

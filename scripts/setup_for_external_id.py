import argparse
import asyncio
import datetime
import os
import random
import time
from typing import Dict, Tuple

import aiohttp
from azure.identity.aio import AzureDeveloperCliCredential

from auth_common import (
    TIMEOUT,
    add_application_owner,
    get_auth_headers,
    get_azure_auth_headers,
    get_current_user,
    get_microsoft_graph_service_principal,
    get_tenant_details,
    test_authentication_enabled,
    create_or_update_application_with_secret,
    wait_for_cache_sync,
    update_azd_env,
)

def create_client_app_payload():
    return {
        "displayName": "azd Application Creation helper",
        "signInAudience": "AzureADMyOrg",
        "requiredResourceAccess": [
            {
                "resourceAppId": "00000003-0000-0000-c000-000000000000",
                "resourceAccess": [
                    # Graph Application.ReadWrite.All
                    {"id": "1bfefb4e-e0b5-418b-a88f-73c46d2cc8e9", "type": "Role"},
                    # Graph EventListener.ReadWrite.All
                    {"id": "0edf5e9e-4ce8-468a-8432-d08631d18c43", "type": "Role"},
                    # Graph DelegatedPermissionGrant.ReadWrite.All
                    {"id": "8e8e4742-1d95-4f68-9d56-6ee75648c72a", "type": "Role"},
                    # Graph Organization.ReadWrite.All
                    {"id": "292d869f-3427-49a8-9dab-8c70152b74e9", "type": "Role"},
                    # Graph User.Read.All
                    {"id": "df021288-bdef-4463-88db-98f22de89214", "type": "Role"},
                ],
            },
        ],
    }


def app_roles() -> str:
    app_roles = [
        # Graph Application.ReadWrite.All
        "1bfefb4e-e0b5-418b-a88f-73c46d2cc8e9",
        # Graph EventListener.ReadWrite.All
        "0edf5e9e-4ce8-468a-8432-d08631d18c43",
        # Graph DelegatedPermissionGrant.ReadWrite.All
        "8e8e4742-1d95-4f68-9d56-6ee75648c72a",
        # Graph Organization.ReadWrite.All
        "292d869f-3427-49a8-9dab-8c70152b74e9",
        # Graph User.Read.All
        "df021288-bdef-4463-88db-98f22de89214",
    ]
    return app_roles


async def grant_approle(auth_headers: Dict[str, str], sp_obj_id: str, resource_id: str, app_role: str):
    async with aiohttp.ClientSession(headers=auth_headers, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as session:
        async with session.post(
            f"https://graph.microsoft.com/v1.0/servicePrincipals/{sp_obj_id}/appRoleAssignments",
            json={"principalId": sp_obj_id, "resourceId": resource_id, "appRoleId": app_role},
        ) as response:
            response_json = await response.json()
            if response.status == 201:
                return response_json["id"]

            raise Exception(response_json)

# 
# for an external ID tenant, the login domain is a subdomain of ciamlogin.com, not onmicrosoft.com
#
def login_domain_for(default_domain: str) -> str:
    prefix = default_domain.split(".")[0]
    return f"{prefix}.ciamlogin.com"

async def main():
    parser = argparse.ArgumentParser(description='Setup External ID Service Principal')
    parser.add_argument('tenant_id',
                        metavar='tenant-id',
                        type=str,
                        help='the External ID TenantId')
    args = parser.parse_args()

    if args.tenant_id is None:
        args.print_help()
        exit(1)
    tenant_id = args.tenant_id
    
    print(f"Setting up External ID Service Principal in tenant {tenant_id}")
    credential = AzureDeveloperCliCredential(tenant_id=tenant_id)
    auth_headers = await get_auth_headers(credential)

    (tenant_type, default_domain) = await get_tenant_details(credential, tenant_id)
    if tenant_type != "CIAM":
        print("You don't need to run this script for non-ExternalId tenant...")
        exit(0)
    # Convert default domain to login domain
    login_domain = login_domain_for(default_domain)
    print(f"Using login domain {login_domain} for tenant {tenant_id}")
   
    # Update azd env
    update_azd_env("AZURE_AUTH_TENANT_ID", tenant_id)
    update_azd_env("AZURE_AUTH_LOGIN_ENDPOINT", login_domain)

    print("Creating application registration...")
    (obj_id, app_id, sp_id) = await create_or_update_application_with_secret(
        auth_headers,
        app_id_env_var="AZURE_AUTH_EXTID_APP_ID",
        app_secret_env_var="AZURE_AUTH_EXTID_APP_SECRET",
        app_payload=create_client_app_payload(),
    )

    print("Granting Application consent...")
    graph_sp_id = await get_microsoft_graph_service_principal(auth_headers)
    for app_role in app_roles():
        print(f"Granting app role {app_role}...")
        await grant_approle(auth_headers, sp_id, graph_sp_id, app_role)

    print(f"Adding application owner for {app_id}")
    owner_id = await get_current_user(auth_headers)
    await add_application_owner(auth_headers, obj_id, owner_id)
    update_azd_env("AZURE_AUTH_EXTID_APP_OWNER", owner_id)


if __name__ == "__main__":
    asyncio.run(main())
"""Explicit, scoped recovery of an already-approved failed invitation.

Does not approve requests, create accounts/workspaces or set a password.
Never prints the token, email, private link or provider response body.
Use once with --request-id; successful invitations are never resent.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def probe_transport() -> None:
    from app.atlas_platform.auth_delivery import USER_AGENT, _provider_error_code, auth_delivery_configuration
    cfg=auth_delivery_configuration()
    if cfg is None or cfg.provider != "resend":
        print('SRIS_INVITATION_PROBE {"skipped":true}')
        return
    result=[]
    for custom in (False,True):
        # Missing sender, recipient AND content: this request cannot send email.
        headers={"Authorization":"Bearer "+os.environ["RESEND_API_KEY"].strip(),"Content-Type":"application/json"}
        if custom: headers["User-Agent"]=USER_AGENT
        req=Request("https://api.resend.com/emails",data=b"{}",headers=headers,method="POST")
        try:
            with urlopen(req,timeout=12) as response:
                result.append({"custom_user_agent":custom,"status":response.status})
        except HTTPError as exc:
            result.append({"custom_user_agent":custom,"status":exc.code,"code":_provider_error_code(exc)})
        except Exception as exc:
            result.append({"custom_user_agent":custom,"error":type(exc).__name__})
        time.sleep(1)
    print("SRIS_INVITATION_PROBE "+json.dumps(result))


def repair(request_id: str) -> dict:
    from app.atlas_platform.audit import record_audit
    from app.atlas_platform.commercial_access_models import AccessRequest
    from app.atlas_platform.database import SessionLocal
    from app.atlas_platform.identity import _new_token, _token_hash, _send_invitation_email, _bounded_env_int, _invitation_status
    from app.atlas_platform.models import UserInvitation, User, Membership, utcnow
    with SessionLocal() as db:
        item=db.query(AccessRequest).filter(AccessRequest.id==request_id).with_for_update().one_or_none()
        if item is None or item.status != "approved" or not item.invitation_id:
            return {"status":"skipped","reason":"no_approved_invitation"}
        invite=db.query(UserInvitation).filter(UserInvitation.id==item.invitation_id).with_for_update().one_or_none()
        if invite is None or invite.accepted_at or invite.revoked_at:
            return {"status":"skipped","reason":"not_recoverable"}
        if invite.email.lower()!=item.email.lower() or invite.organization_id!=item.organization_id:
            raise RuntimeError("invitation_request_mismatch")
        if invite.delivery_status != "failed":
            return {"status":"skipped","reason":"not_failed","delivery_status":invite.delivery_status}
        user=db.query(User).filter(User.email==invite.email.lower()).one_or_none()
        membership=db.query(Membership).filter(Membership.user_id==user.id,Membership.organization_id==invite.organization_id).first() if user else None
        if membership is not None:
            return {"status":"skipped","reason":"already_assigned"}
        raw=_new_token()
        invite.token_hash=_token_hash("invite",raw)
        invite.expires_at=utcnow()+timedelta(hours=_bounded_env_int("SRIS_INVITATION_TTL_HOURS",72,1,24*14))
        invite.delivery_status="pending"
        invite_id=invite.id
        org_id=invite.organization_id
        record_audit(db,action="user.invitation_delivery_recovery_requested",resource_type="user_invitation",
            resource_id=invite_id,organization_id=org_id,user_id=None,
            payload={"source":"explicit_staging_recovery","request_id":request_id,"previous_delivery_status":"failed"})
        db.commit()
    _send_invitation_email(invite_id,raw)
    raw=None
    with SessionLocal() as db:
        invite=db.get(UserInvitation,invite_id)
        result={"request_id":request_id,"delivery_status":invite.delivery_status,
            "invitation_status":_invitation_status(invite),"attempts":invite.delivery_attempts,
            "existing_account":user is not None,"account_created":False,"workspace_created":False}
        record_audit(db,action="user.invitation_delivery_recovery_completed",resource_type="user_invitation",
            resource_id=invite_id,organization_id=org_id,user_id=None,payload=result)
        db.commit()
    return result


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--request-id",required=True)
    parser.add_argument("--probe",action="store_true")
    args=parser.parse_args()
    if os.getenv("RAILWAY_SERVICE_ID")!="5adcd02c-c875-499f-bd3b-b4d5ea256258" or os.getenv("RAILWAY_ENVIRONMENT_ID")!="625472d4-144c-460a-b152-d1890f1f80db":
        raise SystemExit("Recovery restricted to explicitly authorized SRIS staging")
    if args.probe: probe_transport()
    print("SRIS_INVITATION_RECOVERY "+json.dumps(repair(args.request_id),sort_keys=True))

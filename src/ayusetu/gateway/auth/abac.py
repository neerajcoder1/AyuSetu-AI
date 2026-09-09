"""
ABAC (Attribute-Based Access Control) & Resource Scope Engine
=============================================================
Evaluates dynamic attribute-based rules, encounter scoping, IDOR protection,
temporal validity, separation of duties, and emergency break-glass overrides per PRD §21.4.
"""

from typing import Tuple
from ayusetu.gateway.auth.models import (
    Action,
    AuthContext,
    Principal,
    Resource,
    Role,
)
from ayusetu.gateway.auth.rbac import RBACPolicy

# Roles eligible for emergency break-glass encounter override per PRD §21.4
BREAK_GLASS_ELIGIBLE_ROLES = {Role.PHYSICIAN, Role.NURSE, Role.ATTENDANT}


class ABACEvaluator:
    """Evaluates contextual authorization rules after RBAC static evaluation."""

    @classmethod
    def evaluate(cls, ctx: AuthContext) -> Tuple[bool, str]:
        """
        Evaluate full authorization context (RBAC + ABAC + Break-glass).
        Returns: (allowed: bool, reason: str)
        """
        principal = ctx.principal

        # 1. Evaluate RBAC Static Matrix
        if not RBACPolicy.is_permitted(principal.role, ctx.resource, ctx.action):
            # If not statically permitted, can ONLY proceed if valid Break-Glass is active for eligible role
            if not (ctx.break_glass and ctx.break_glass.is_break_glass):
                return False, "Action not permitted for principal role"
            if principal.role not in BREAK_GLASS_ELIGIBLE_ROLES:
                return False, "Principal role not eligible for break-glass emergency override"
            if not ctx.break_glass.reason or len(ctx.break_glass.reason.strip()) < 5:
                return False, "A valid clinical reason is mandatory for break-glass access"

        # 2. Patient / Companion Ownership Scope (IDOR Prevention)
        if principal.role in (Role.PATIENT, Role.COMPANION):
            # Must own the target encounter or patient resource
            if ctx.target_encounter_id and principal.encounter_id:
                if str(ctx.target_encounter_id) != str(principal.encounter_id):
                    return False, "Access denied to foreign encounter record"
            if ctx.target_patient_id and principal.patient_id:
                if str(ctx.target_patient_id) != str(principal.patient_id):
                    return False, "Access denied to foreign patient record"

        # 3. Clinical Staff Encounter Scope & Break-Glass Override
        if principal.role in (Role.PHYSICIAN, Role.NURSE, Role.ATTENDANT):
            if ctx.target_encounter_id:
                is_assigned = (
                    str(ctx.target_encounter_id) in principal.assigned_encounter_ids
                    or (principal.encounter_id and str(ctx.target_encounter_id) == str(principal.encounter_id))
                )
                
                # Check department alignment if configured
                dept_match = (
                    principal.department is None
                    or ctx.target_department is None
                    or principal.department == ctx.target_department
                )

                if not (is_assigned and dept_match):
                    # Evaluate Break-Glass override
                    if ctx.break_glass and ctx.break_glass.is_break_glass:
                        if principal.role not in BREAK_GLASS_ELIGIBLE_ROLES:
                            return False, "Principal role not eligible for break-glass emergency override"
                        if not ctx.break_glass.reason or len(ctx.break_glass.reason.strip()) < 5:
                            return False, "A valid clinical reason is mandatory for break-glass access"
                        # Break-glass granted immediately
                        return True, "Granted via break-glass emergency override"
                    else:
                        return False, "Encounter not assigned to staff member in active department today"

        # 4. Temporal Scope (Access to signed records expires 72h post-encounter, except MRD)
        if ctx.resource == Resource.SIGNED_CLINICAL_RECORD:
            if principal.role != Role.MRD and ctx.encounter_age_hours is not None:
                if ctx.encounter_age_hours > 72.0:
                    # Allow break-glass override if emergency
                    if ctx.break_glass and ctx.break_glass.is_break_glass:
                        return True, "Granted via break-glass past 72-hour window"
                    return False, "Access expired: signed clinical records close after 72 hours"

        # 5. Separation of Duties (Clinical content author cannot self-approve)
        if ctx.resource == Resource.CLINICAL_CONTENT and ctx.action in (Action.CREATE, Action.UPDATE, Action.SIGN):
            if ctx.is_author:
                return False, "Separation of duties: author cannot approve own clinical content"

        return True, "Authorized"

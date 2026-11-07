"""Pydantic request/response models. Field names use camelCase to match the frontend."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


# ---------- Triage ----------
class TriageRecommendRequest(CamelModel):
    chief: str
    duration: str = ""
    bodyPart: str = ""
    severity: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    extra: Optional[str] = None


class DepartmentRec(CamelModel):
    id: str
    name: str
    reason: str
    rank: int


class TriageResult(CamelModel):
    departments: list[DepartmentRec]
    urgency: Literal["emergency", "urgent", "routine"]
    suggestOnline: bool
    nextSteps: list[str]
    disclaimer: str
    source: str = "mock"
    error: Optional[str] = None
    message: Optional[str] = None
    summary: Optional[str] = None
    # Structured consult summary
    chiefComplaint: Optional[str] = None
    accompanying: Optional[list[str]] = None


# ---------- Consult ----------
class ConsultMessage(CamelModel):
    role: Literal["user", "assistant", "system"]
    content: str
    createdAt: Optional[str] = None


class CreateSessionResponse(CamelModel):
    id: str
    messages: list[ConsultMessage] = Field(default_factory=list)
    status: Literal["active", "completed"] = "active"
    triage: Optional[TriageResult] = None


class PostMessageRequest(CamelModel):
    content: str
    # Optional body flag; query ?stream=1 / Accept: text/event-stream also work
    stream: Optional[bool] = None


class PostMessageResponse(CamelModel):
    id: str
    messages: list[ConsultMessage]
    status: Literal["active", "completed"]
    reply: ConsultMessage
    triage: Optional[TriageResult] = None
    disclaimer: str
    source: str = "mock"
    error: Optional[str] = None
    message: Optional[str] = None


# ---------- Catalog ----------
class Department(CamelModel):
    id: str
    name: str
    intro: str = ""
    location: str = ""
    tips: str = ""


class Doctor(CamelModel):
    id: str
    departmentId: str
    name: str
    title: str
    intro: str = ""


class Slot(CamelModel):
    id: str
    doctorId: str
    date: str
    time: str
    remaining: int
    available: bool = True


# ---------- Appointments ----------
class CreateAppointmentRequest(CamelModel):
    departmentId: str
    doctorId: str
    slotId: str
    patientName: str
    phone: Optional[str] = None
    chief: Optional[str] = None
    triageSessionId: Optional[str] = None


class PatchAppointmentRequest(CamelModel):
    status: Optional[Literal["pending", "confirmed", "cancelled"]] = None


class Appointment(CamelModel):
    id: str
    departmentId: str
    departmentName: str
    doctorId: str
    doctorName: str
    slotId: str
    date: str
    time: str
    patientName: str
    phone: Optional[str] = None
    chief: Optional[str] = None
    triageSessionId: Optional[str] = None
    status: Literal["pending", "confirmed", "cancelled"]
    createdAt: str


# ---------- Previsit report (医生看的预问诊摘要) ----------
class PrevisitReportRequest(CamelModel):
    """Provide sessionId and/or structured fields. sessionId takes session facts/triage when present."""

    sessionId: Optional[str] = None
    chiefComplaint: Optional[str] = None
    duration: Optional[str] = None
    bodyPart: Optional[str] = None
    accompanying: Optional[list[str]] = None
    pastHistory: Optional[str] = None
    allergies: Optional[str] = None
    medications: Optional[str] = None
    patientNotes: Optional[str] = None
    urgency: Optional[Literal["emergency", "urgent", "routine"]] = None
    departments: Optional[list[DepartmentRec]] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    extra: Optional[str] = None


class PrevisitReport(CamelModel):
    chiefComplaint: str
    presentIllness: str
    accompanying: list[str] = Field(default_factory=list)
    relevantHistory: str = ""
    urgency: Literal["emergency", "urgent", "routine"]
    suggestedDepartments: list[DepartmentRec] = Field(default_factory=list)
    patientNarrative: str = ""
    redFlags: list[str] = Field(default_factory=list)
    doctorHints: list[str] = Field(default_factory=list)
    summaryText: str = ""
    disclaimer: str
    source: str = "mock"
    sessionId: Optional[str] = None
    generatedAt: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None


# ---------- Lab / imaging report interpretation ----------
class ReportInterpretRequest(CamelModel):
    text: str = ""
    reportType: Optional[Literal["lab", "imaging", "other"]] = None
    reportId: Optional[str] = None


class ReportAbnormality(CamelModel):
    item: str
    finding: str
    severity: Literal["high", "moderate", "low", "info"] = "info"


class ReportInterpretResult(CamelModel):
    interpretation: str
    abnormalities: list[ReportAbnormality] = Field(default_factory=list)
    advice: list[str] = Field(default_factory=list)
    disclaimer: str
    source: str = "mock"
    reportType: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None


# ---------- Patients ----------
class CreatePatientRequest(CamelModel):
    name: str
    gender: str = "未知"
    age: int = 0
    relation: Optional[str] = "self"


class PatchPatientRequest(CamelModel):
    name: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    relation: Optional[str] = None


class HealthProfile(CamelModel):
    allergies: list[str] = Field(default_factory=list)
    chronicDiseases: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    bloodType: Optional[str] = ""
    notes: Optional[str] = ""


class CreateSessionRequest(CamelModel):
    patientId: Optional[str] = None


class CreatePreconsultFromSessionRequest(CamelModel):
    patientId: Optional[str] = None


class CreatePreconsultRequest(CamelModel):
    sessionId: str
    patientId: Optional[str] = None


# ---------- M2 Waiting / Messages / Navigation ----------
class CheckInRequest(CamelModel):
    appointmentId: str


class WaitingStatusItem(CamelModel):
    id: str
    appointmentId: str
    patientName: str = ""
    departmentId: str = ""
    departmentName: str = ""
    doctorId: str = ""
    doctorName: str = ""
    date: str = ""
    time: str = ""
    status: Literal["not_checked_in", "waiting", "called", "done"]
    queueNo: int = 0
    aheadCount: int = 0
    checkedInAt: Optional[str] = None
    calledAt: Optional[str] = None
    doneAt: Optional[str] = None
    updatedAt: Optional[str] = None
    createdAt: Optional[str] = None
    location: Optional[str] = None
    tips: Optional[str] = None
    disclaimer: Optional[str] = None


class MessageItem(CamelModel):
    id: str
    title: str
    body: str
    type: Literal["appointment_reminder", "report_ready", "system"]
    read: bool = False
    createdAt: str
    link: Optional[str] = None


class NavigationDepartment(CamelModel):
    id: str
    name: str
    intro: str = ""
    location: str = ""
    tips: str = ""


# ---------- M3 Refills / Medications / Follow-ups ----------
class CreateRefillRequest(CamelModel):
    patientId: Optional[str] = None
    medicationName: str
    dosage: Optional[str] = None
    quantity: Optional[str] = None
    reason: Optional[str] = None
    departmentId: Optional[str] = None


class PatchRefillRequest(CamelModel):
    status: Literal["pending", "approved", "rejected", "cancelled"]
    reviewNote: Optional[str] = None


class CreateMedicationReminderRequest(CamelModel):
    patientId: Optional[str] = None
    drugName: str
    dose: str = ""
    frequency: str = ""
    times: list[str] = Field(default_factory=list)
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    enabled: Optional[bool] = True


class PatchMedicationReminderRequest(CamelModel):
    patientId: Optional[str] = None
    drugName: Optional[str] = None
    dose: Optional[str] = None
    frequency: Optional[str] = None
    times: Optional[list[str]] = None
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    enabled: Optional[bool] = None
    # mark a specific time as taken today, e.g. "08:00"
    takenTime: Optional[str] = None
    # clear taken for a time
    untakenTime: Optional[str] = None


class FollowupSubmitRequest(CamelModel):
    patientId: Optional[str] = None
    answers: dict[str, object] = Field(default_factory=dict)


# ---------- M4 Bills / Identity / Audit ----------
class PayBillResponseNote(CamelModel):
    """Marker; bills use plain dicts from store."""

    pass


class UpdateIdentityRequest(CamelModel):
    realName: Optional[str] = None
    idNumber: Optional[str] = None
    visitCardNo: Optional[str] = None


# ---------- M5 Doctor-consult / Consultations (图文/视频接诊) ----------
class CreateDoctorConsultSessionRequest(CamelModel):
    mode: Literal["text", "video"] = "text"
    patientId: Optional[str] = None
    chiefComplaint: Optional[str] = None
    departmentName: Optional[str] = None
    departmentId: Optional[str] = None
    doctorId: Optional[str] = None


class CreateConsultationRequest(CamelModel):
    """兼容别名 body：type 或 mode."""
    type: Optional[Literal["text", "video"]] = None
    mode: Optional[Literal["text", "video"]] = None
    patientId: Optional[str] = None
    departmentId: Optional[str] = None
    departmentName: Optional[str] = None
    doctorId: Optional[str] = None
    chief: Optional[str] = None
    chiefComplaint: Optional[str] = None
    reason: Optional[str] = None


class PostConsultationMessageRequest(CamelModel):
    content: str
    role: Optional[Literal["patient", "doctor"]] = None
    senderRole: Optional[Literal["patient", "doctor"]] = None


class DoctorReplyRequest(CamelModel):
    content: str


class EndDoctorConsultRequest(CamelModel):
    summary: Optional[str] = None


class PatchConsultationStatusRequest(CamelModel):
    status: Literal["queued", "waiting_doctor", "in_progress", "ended"]


# ---------- M6 Lab/Exam bookings (检查检验预约，独立于门诊预约) ----------
class CreateLabExamBookingRequest(CamelModel):
    examId: str
    slotId: str
    patientId: Optional[str] = None
    patientName: Optional[str] = None


class PatchLabExamBookingRequest(CamelModel):
    """改约或取消。改约：slotId 或 date+time；取消：status=cancelled。"""

    slotId: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    status: Optional[Literal["cancelled", "confirmed"]] = None


# ---------- M6 product UI contract (/api/exam-items, /api/exam-bookings) ----------
class CreateUiExamBookingRequest(CamelModel):
    itemId: str
    slotId: str
    date: Optional[str] = None
    patientId: Optional[str] = None
    note: Optional[str] = None
    patientName: Optional[str] = None


class RescheduleUiExamBookingRequest(CamelModel):
    slotId: str
    date: Optional[str] = None


class CancelUiExamBookingRequest(CamelModel):
    reason: Optional[str] = None


# ---------- M7 Pharmacy / 药品配送 Mock ----------
class CreatePharmacyAddressRequest(CamelModel):
    name: str
    phone: str
    province: str = ""
    city: str = ""
    district: str = ""
    detail: str
    isDefault: Optional[bool] = None
    patientId: Optional[str] = None


class UpdatePharmacyAddressRequest(CamelModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    detail: Optional[str] = None
    isDefault: Optional[bool] = None
    patientId: Optional[str] = None


class CreatePharmacyDeliveryRequest(CamelModel):
    orderId: str
    addressId: str
    patientId: Optional[str] = None


class AdvancePharmacyDeliveryRequest(CamelModel):
    """Optional target status; accepts canonical or UI alias."""

    status: Optional[str] = None
    uiStatus: Optional[str] = None


class CancelPharmacyDeliveryRequest(CamelModel):
    reason: Optional[str] = None

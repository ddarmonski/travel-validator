from datetime import datetime
import uuid

class Expense:
    def __init__(self, id=None, category=None, description=None, amount=0, date=None, **kwargs):
        self.id = id or str(uuid.uuid4())
        self.category = category
        self.description = description
        self.amount = amount
        self.date = date or datetime.utcnow().isoformat()

    def to_dict(self):
        return {
            'id': self.id,
            'category': self.category,
            'description': self.description,
            'amount': self.amount,
            'date': self.date
        }

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

class Document:
    def __init__(self, id=None, file_name=None, file_size=0, file_url=None, **kwargs):
        self.id = id or str(uuid.uuid4())
        self.file_name = file_name
        self.file_size = file_size
        self.file_url = file_url
        self.uploaded_at = kwargs.get('uploaded_at', datetime.utcnow().isoformat())

    def to_dict(self):
        return {
            'id': self.id,
            'file_name': self.file_name,
            'file_size': self.file_size,
            'file_url': self.file_url,
            'uploaded_at': self.uploaded_at
        }

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

class RequestHistory:
    def __init__(self, id=None, type=None, title=None, user=None, comments=None, **kwargs):
        self.id = id or str(uuid.uuid4())
        self.type = type
        self.title = title
        self.user = user
        self.comments = comments
        self.date = kwargs.get('date', datetime.utcnow().isoformat())

    def to_dict(self):
        return {
            'id': self.id,
            'type': self.type,
            'title': self.title,
            'user': self.user,
            'comments': self.comments,
            'date': self.date
        }

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

class TravelRequest:
    def __init__(self, id=None, requester=None, status="PENDING", **kwargs):
        self.id = id or str(uuid.uuid4())
        self.type = "travel_request"
        self.requester = requester
        self.status = status
        self.created_at = kwargs.get('created_at', datetime.utcnow().isoformat())
        self.updated_at = kwargs.get('updated_at', datetime.utcnow().isoformat())
        self.start_date = kwargs.get('start_date')
        self.end_date = kwargs.get('end_date')
        self.total_amount = kwargs.get('total_amount', 0)
        self.department = kwargs.get('department')
        self.position = kwargs.get('position')
        self.documents = [Document.from_dict(doc) if isinstance(doc, dict) else doc for doc in kwargs.get('documents', [])]
        self.expenses = [Expense.from_dict(exp) if isinstance(exp, dict) else exp for exp in kwargs.get('expenses', [])]
        self.history = [RequestHistory.from_dict(hist) if isinstance(hist, dict) else hist for hist in kwargs.get('history', [])]

    def to_dict(self):
        return {
            'id': self.id,
            'type': self.type,
            'requester': self.requester,
            'status': self.status,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'total_amount': self.total_amount,
            'department': self.department,
            'position': self.position,
            'documents': [doc.to_dict() for doc in self.documents],
            'expenses': [exp.to_dict() for exp in self.expenses],
            'history': [hist.to_dict() for hist in self.history]
        }

    @classmethod
    def from_dict(cls, data):
        return cls(**data)
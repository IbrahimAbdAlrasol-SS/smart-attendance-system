# backend/app/utils/swagger.py
"""Swagger/OpenAPI configuration for the application."""
from flask import Blueprint, jsonify
from flask_swagger_ui import get_swaggerui_blueprint

# Swagger UI configuration
SWAGGER_URL = '/api/docs'
API_URL = '/api/swagger.json'

def get_swagger_blueprint():
    """Create and return swagger UI blueprint."""
    swaggerui_blueprint = get_swaggerui_blueprint(
        SWAGGER_URL,
        API_URL,
        config={
            'app_name': "Smart Attendance System API",
            'defaultModelsExpandDepth': -1,
            'defaultModelExpandDepth': 1,
            'docExpansion': 'list',
            'filter': True,
            'showExtensions': True,
            'showCommonExtensions': True,
            'supportedSubmitMethods': ['get', 'post', 'put', 'delete', 'patch'],
            'validatorUrl': None,
        }
    )
    return swaggerui_blueprint

def generate_swagger_spec():
    """Generate OpenAPI/Swagger specification."""
    return {
        "openapi": "3.0.0",
        "info": {
            "title": "Smart Attendance System API",
            "description": "نظام حضور ذكي للجامعات مع تحقق ثلاثي (QR + GPS + Face Recognition)",
            "version": "1.0.0",
            "contact": {
                "name": "API Support",
                "email": "support@university.edu"
            }
        },
        "servers": [
            {
                "url": "http://127.0.0.1:5000/api",
                "description": "Development server"
            },
            {
                "url": "https://api.smart-attendance.com/api",
                "description": "Production server"
            }
        ],
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT"
                }
            },
            "schemas": {
                "User": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "email": {"type": "string", "format": "email"},
                        "name": {"type": "string"},
                        "role": {"type": "string", "enum": ["student", "teacher", "coordinator", "admin"]},
                        "section": {"type": "string", "enum": ["A", "B"], "nullable": True},
                        "created_at": {"type": "string", "format": "date-time"}
                    }
                },
                "Lecture": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "room": {"type": "string"},
                        "teacher_id": {"type": "integer"},
                        "start_time": {"type": "string", "format": "date-time"},
                        "end_time": {"type": "string", "format": "date-time"},
                        "location": {
                            "type": "object",
                            "properties": {
                                "latitude": {"type": "number"},
                                "longitude": {"type": "number"}
                            }
                        }
                    }
                },
                "AttendanceRecord": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "student_id": {"type": "integer"},
                        "lecture_id": {"type": "integer"},
                        "check_in_time": {"type": "string", "format": "date-time"},
                        "verification_method": {"type": "string", "enum": ["qr", "manual", "emergency"]},
                        "is_present": {"type": "boolean"}
                    }
                },
                "QRCode": {
                    "type": "object",
                    "properties": {
                        "qr_code": {"type": "string"},
                        "qr_image": {"type": "string", "description": "Base64 encoded QR image"},
                        "lecture_id": {"type": "integer"},
                        "expires_at": {"type": "string", "format": "date-time"},
                        "expires_in": {"type": "integer", "description": "Seconds until expiry"}
                    }
                },
                "Error": {
                    "type": "object",
                    "properties": {
                        "error": {"type": "boolean"},
                        "message": {"type": "string"},
                        "status_code": {"type": "integer"}
                    }
                },
                "Success": {
                    "type": "object",
                    "properties": {
                        "error": {"type": "boolean", "default": False},
                        "message": {"type": "string"},
                        "data": {"type": "object"}
                    }
                }
            }
        },
        "paths": {
            "/auth/register": {
                "post": {
                    "tags": ["Authentication"],
                    "summary": "Register new user",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["email", "password", "name"],
                                    "properties": {
                                        "email": {"type": "string", "format": "email"},
                                        "password": {"type": "string", "minLength": 6},
                                        "name": {"type": "string", "minLength": 2},
                                        "role": {"type": "string", "enum": ["student", "teacher"]}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "description": "User created successfully",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Success"}
                                }
                            }
                        },
                        "400": {
                            "description": "Validation error",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Error"}
                                }
                            }
                        }
                    }
                }
            },
            "/auth/login": {
                "post": {
                    "tags": ["Authentication"],
                    "summary": "User login",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["email", "password"],
                                    "properties": {
                                        "email": {"type": "string", "format": "email"},
                                        "password": {"type": "string"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Login successful",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "error": {"type": "boolean"},
                                            "message": {"type": "string"},
                                            "data": {
                                                "type": "object",
                                                "properties": {
                                                    "access_token": {"type": "string"},
                                                    "refresh_token": {"type": "string"},
                                                    "user": {"$ref": "#/components/schemas/User"}
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "401": {
                            "description": "Invalid credentials",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Error"}
                                }
                            }
                        }
                    }
                }
            },
            "/auth/me": {
                "get": {
                    "tags": ["Authentication"],
                    "summary": "Get current user profile",
                    "security": [{"bearerAuth": []}],
                    "responses": {
                        "200": {
                            "description": "User profile",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Success"}
                                }
                            }
                        },
                        "401": {
                            "description": "Unauthorized",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Error"}
                                }
                            }
                        }
                    }
                }
            },
            "/lectures": {
                "get": {
                    "tags": ["Lectures"],
                    "summary": "Get all lectures",
                    "security": [{"bearerAuth": []}],
                    "parameters": [
                        {
                            "name": "page",
                            "in": "query",
                            "schema": {"type": "integer", "default": 1}
                        },
                        {
                            "name": "per_page",
                            "in": "query",
                            "schema": {"type": "integer", "default": 10}
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "List of lectures",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Success"}
                                }
                            }
                        }
                    }
                },
                "post": {
                    "tags": ["Lectures"],
                    "summary": "Create new lecture",
                    "security": [{"bearerAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["title", "room", "start_time", "end_time"],
                                    "properties": {
                                        "title": {"type": "string"},
                                        "description": {"type": "string"},
                                        "room": {"type": "string"},
                                        "start_time": {"type": "string", "format": "date-time"},
                                        "end_time": {"type": "string", "format": "date-time"},
                                        "latitude": {"type": "number"},
                                        "longitude": {"type": "number"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "description": "Lecture created",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Success"}
                                }
                            }
                        }
                    }
                }
            },
            "/lectures/{lecture_id}/qr": {
                "post": {
                    "tags": ["QR Codes"],
                    "summary": "Generate QR code for lecture",
                    "security": [{"bearerAuth": []}],
                    "parameters": [
                        {
                            "name": "lecture_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"}
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "QR code generated",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "error": {"type": "boolean"},
                                            "message": {"type": "string"},
                                            "data": {"$ref": "#/components/schemas/QRCode"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/attendance/checkin": {
                "post": {
                    "tags": ["Attendance"],
                    "summary": "Check-in to lecture",
                    "security": [{"bearerAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["qr_code", "location"],
                                    "properties": {
                                        "qr_code": {"type": "string"},
                                        "location": {
                                            "type": "object",
                                            "properties": {
                                                "latitude": {"type": "number"},
                                                "longitude": {"type": "number"}
                                            }
                                        },
                                        "face_data": {"type": "string", "description": "Base64 encoded face data"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Check-in successful",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Success"}
                                }
                            }
                        },
                        "400": {
                            "description": "Invalid QR or location",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Error"}
                                }
                            }
                        }
                    }
                }
            },
            "/attendance/my-records": {
                "get": {
                    "tags": ["Attendance"],
                    "summary": "Get my attendance records",
                    "security": [{"bearerAuth": []}],
                    "responses": {
                        "200": {
                            "description": "Attendance records",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Success"}
                                }
                            }
                        }
                    }
                }
            },
            "/reports/{type}": {
                "get": {
                    "tags": ["Reports"],
                    "summary": "Generate attendance report",
                    "security": [{"bearerAuth": []}],
                    "parameters": [
                        {
                            "name": "type",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "enum": ["daily", "weekly", "monthly"]}
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Report generated",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Success"}
                                }
                            }
                        }
                    }
                }
            }
        },
        "tags": [
            {
                "name": "Authentication",
                "description": "User authentication and authorization"
            },
            {
                "name": "Lectures",
                "description": "Lecture management"
            },
            {
                "name": "QR Codes",
                "description": "QR code generation and validation"
            },
            {
                "name": "Attendance",
                "description": "Attendance tracking"
            },
            {
                "name": "Reports",
                "description": "Attendance reports and analytics"
            }
        ]
    }
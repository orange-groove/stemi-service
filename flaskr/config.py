import os

class Config:
    """Base config class"""
    SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://wprjqpjfxzjrxlutwzbc.supabase.co')
    SUPABASE_KEY = os.getenv('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6IndwcmpxcGpmeHpqcnhsdXR3emJjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MjQyNjY1NjUsImV4cCI6MjAzOTg0MjU2NX0.TGjPKSuUPd3MRD7hCmfb5AKy5mBMLfg-Vqa1V30Kjx4')
    SUPABASE_BUCKET = os.getenv('SUPABASE_BUCKET', 'yoke-stems')
    RUNPOD_API_KEY = os.getenv('RUNPOD_API_KEY')
    RUNPOD_ENDPOINT_ID = os.getenv('RUNPOD_ENDPOINT_ID', 'maxm6b2amueuny')
    SECRET_KEY = 'hSsvtllNKbRmmfxHowboCUBd4/8ESrAbv/IAq4BGLUPqRrBfWhztEaC/ryQ1fVriJId1Obp1AC0wzYAt+7T4vw=='
    # Stripe
    STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
    STRIPE_PRICE_ID = os.getenv('STRIPE_PRICE_ID')
    STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')

class DevelopmentConfig(Config):
    """Development configurations"""
    DEBUG = True

class ProductionConfig(Config):
    """Production configurations"""
    DEBUG = False

import os

class Config:
    """Base config class"""
    SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://wprjqpjfxzjrxlutwzbc.supabase.co')
    SUPABASE_KEY = os.getenv('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6IndwcmpxcGpmeHpqcnhsdXR3emJjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MjQyNjY1NjUsImV4cCI6MjAzOTg0MjU2NX0.TGjPKSuUPd3MRD7hCmfb5AKy5mBMLfg-Vqa1V30Kjx4')
    SUPABASE_BUCKET = os.getenv('SUPABASE_BUCKET', 'yoke-stems')

class DevelopmentConfig(Config):
    """Development configurations"""
    DEBUG = True

class ProductionConfig(Config):
    """Production configurations"""
    DEBUG = False

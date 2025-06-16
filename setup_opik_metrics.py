#!/usr/bin/env python3
"""
Opik Metrics Testing Script with Multiple Provider Support

This script demonstrates how to use Opik for tracing and metrics collection
with various LLM providers including OpenAI, Anthropic, and others.
"""

import os
import sys
from opik import track

# Set Opik configuration
os.environ["OPIK_URL_OVERRIDE"] = "http://localhost:5173/api"

def check_api_keys():
    """Check which API keys are available"""
    keys = {
        'OpenAI': os.environ.get('OPENAI_API_KEY') or os.environ.get('API_KEY_OPENAI'),
        'Anthropic': os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('API_KEY_ANTHROPIC'),
        'Google': os.environ.get('GOOGLE_API_KEY') or os.environ.get('API_KEY_GOOGLE'),
    }
    
    available_keys = [provider for provider, key in keys.items() if key and not key.startswith('§§')]
    return available_keys, keys

@track
def test_openai_metrics():
    """Test OpenAI integration with Opik metrics"""
    try:
        import openai
        from opik.integrations.openai import track_openai
        
        client = track_openai(openai.OpenAI())
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Say hello and explain what you can do in one sentence."}],
            temperature=0.7,
            max_tokens=50
        )
        
        result = response.choices[0].message.content
        print(f"✅ OpenAI Response: {result}")
        return result
        
    except Exception as e:
        print(f"❌ OpenAI Error: {e}")
        return None

@track  
def test_anthropic_metrics():
    """Test Anthropic integration with Opik metrics"""
    try:
        import anthropic
        from opik.integrations.anthropic import track_anthropic
        
        client = track_anthropic(anthropic.Anthropic())
        
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=50,
            messages=[{"role": "user", "content": "Say hello and explain what you can do in one sentence."}]
        )
        
        result = response.content[0].text
        print(f"✅ Anthropic Response: {result}")
        return result
        
    except Exception as e:
        print(f"❌ Anthropic Error: {e}")
        return None

@track
def test_basic_function_tracing():
    """Test basic function tracing without external APIs"""
    
    @track
    def calculate_metrics(data):
        """Simulate some computation"""
        total = sum(data)
        average = total / len(data) if data else 0
        return {"total": total, "average": average, "count": len(data)}
    
    @track
    def process_data(input_data):
        """Process data and calculate metrics"""
        processed = [x * 2 for x in input_data]
        metrics = calculate_metrics(processed)
        return {
            "original": input_data,
            "processed": processed,
            "metrics": metrics
        }
    
    # Test with sample data
    sample_data = [1, 2, 3, 4, 5]
    result = process_data(sample_data)
    
    print(f"✅ Basic Function Tracing Result: {result}")
    return result

def main():
    """Main test function"""
    print("🚀 Testing Opik Integration with Multiple Providers")
    print("=" * 60)
    
    # Check available API keys
    available_providers, all_keys = check_api_keys()
    
    print(f"📊 Available Providers: {available_providers}")
    print(f"📈 Dashboard URL: http://localhost:5173")
    print("=" * 60)
    
    # Test basic function tracing (always works)
    print("\n1️⃣ Testing Basic Function Tracing (No API required)")
    test_basic_function_tracing()
    
    # Test OpenAI if available
    if 'OpenAI' in available_providers:
        print("\n2️⃣ Testing OpenAI Integration")
        test_openai_metrics()
    else:
        print(f"\n⚠️ OpenAI API key not available. Set OPENAI_API_KEY environment variable.")
        print("   Current value:", all_keys['OpenAI'])
    
    # Test Anthropic if available
    if 'Anthropic' in available_providers:
        print("\n3️⃣ Testing Anthropic Integration")
        test_anthropic_metrics()
    else:
        print(f"\n⚠️ Anthropic API key not available. Set ANTHROPIC_API_KEY environment variable.")
        print("   Current value:", all_keys['Anthropic'])
    
    print("\n" + "=" * 60)
    print("🎯 Test Complete! Check your Opik dashboard for metrics:")
    print("📊 Dashboard: http://localhost:5173")
    print("📈 Metrics include: execution time, function calls, API usage")
    print("🔍 Look for traces from this test session")

if __name__ == "__main__":
    main()
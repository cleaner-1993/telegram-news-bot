import requests
import feedparser
import html
import re
import time
import json
import os

# Fetch the secrets from environment variables
API_KEY = os.getenv('API_KEY')
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')

# CBC Canada News RSS Feed URL
RSS_FEED_URL = 'https://rss.cbc.ca/lineup/canada.xml'

# Gemini API endpoint
URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={API_KEY}"

def fetch_rss_feed():
    """Fetch the RSS feed from CBC."""
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(RSS_FEED_URL, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching the RSS feed: {e}")
        return None

def parse_rss_feed(feed_content):
    """Parse the RSS feed and extract articles."""
    feed = feedparser.parse(feed_content)
    if not feed.entries:
        print("No articles found in the RSS feed.")
        return []
    
    articles = []
    for entry in feed.entries[:5]:  # Fetch only the first 5 articles
        title = entry.title
        description_html = entry.description
        link = entry.link
        published = entry.published if 'published' in entry else 'N/A'
        
        description = extract_text_from_description(description_html)
        image_url = extract_image_from_description(description_html)
        
        articles.append({
            'title': title,
            'description': description,
            'link': link,
            'published': published,
            'image_url': image_url
        })
    
    return articles

def extract_text_from_description(description_html):
    """Extract text content from the HTML description."""
    description_text = re.sub(r'<img[^>]+>', '', description_html)
    description_text = re.sub(r'<[^>]+>', '', description_text)
    description_text = description_text.strip()
    description_text = html.unescape(description_text)
    return description_text

def extract_image_from_description(description_html):
    """Extract image URL from the description HTML."""
    match = re.search(r'<img[^>]+src=["\'](.*?)["\']', description_html)
    return match.group(1) if match else None

def generate_translation(content):
    """Send content to Gemini API for translation to Farsi."""
    headers = {"Content-Type": "application/json"}
    
    # Simplified prompt for translation
    prompt = f"""
    Translate the following text to Farsi. Only provide the translation in Farsi without any English content.
    "{content}"
    """
    
    data = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    try:
        response = requests.post(URL, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        translated_text = get_response_content(response.json())
        return translated_text
    except requests.exceptions.RequestException as e:
        print(f"Translation request failed: {e}")
        return None

def get_response_content(response):
    """Extract the translated text from the API response."""
    try:
        return response['candidates'][0]['content']['parts'][0]['text']
    except (KeyError, IndexError):
        return "No content available."

def send_message(text, image_url=None):
    """Send the translated content to the Telegram channel."""
    text = text.strip()

    if image_url:
        if len(text) > 1024:
            text = text[:1020] + '...'
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        payload = {
            'chat_id': CHANNEL_ID,
            'photo': image_url,
            'caption': text,
            'parse_mode': 'HTML'
        }
    else:
        if len(text) > 4096:
            text = text[:4092] + '...'
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': CHANNEL_ID,
            'text': text,
            'parse_mode': 'HTML'
        }
    
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error sending message: {e}")

def post_news_to_channel():
    """Fetch, translate, and post news articles to the Telegram channel."""
    feed_content = fetch_rss_feed()
    if feed_content:
        articles = parse_rss_feed(feed_content)
        if articles:
            for article in articles:
                title = article['title']
                description = article['description']
                link = article['link']
                published = article['published']
                image_url = article['image_url']
                
                # Translate the title and description separately
                translated_title = generate_translation(title)
                translated_description = generate_translation(description)
                
                if not translated_title or not translated_description:
                    print(f"Skipping article '{title}' due to translation error.")
                    continue

                # Construct the message with translated title and description
                message = (
                    f"<b>{html.escape(translated_title)}</b>\n\n"
                    f"{html.escape(translated_description)}\n\n"
                    f"<a href=\"{html.escape(link)}\">بیشتر بخوانید</a>\n"
                    f"<i>Published on: {html.escape(published)}</i>"
                )
                
                print(f"Posting article: {translated_title}")
                send_message(message, image_url)
                time.sleep(2)

if __name__ == "__main__":
    post_news_to_channel()

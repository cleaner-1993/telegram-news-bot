import requests
import feedparser
import os
import html
import time
from bs4 import BeautifulSoup

# Embed the API keys directly here (replace with your keys)
API_KEY = "YOUR_API_KEY"
BOT_TOKEN = "YOUR_BOT_TOKEN"
CHANNEL_ID = "YOUR_CHANNEL_ID"

# RSS Feed URL
RSS_FEED_URL = 'https://rss.cbc.ca/lineup/canada.xml'

# Gemini API endpoint
URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={API_KEY}"

# File to store published article links
PUBLISHED_FILE = "published_articles.txt"

def fetch_rss_feed():
    """Fetch the RSS feed and extract entries."""
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(RSS_FEED_URL, headers=headers, timeout=10)
        response.raise_for_status()
        feed = feedparser.parse(response.text)
        return feed.entries[:5]  # Return the latest 5 entries
    except requests.exceptions.RequestException as e:
        print(f"Error fetching the RSS feed: {e}")
        return []

def read_published_articles():
    """Read the list of previously published article links."""
    if not os.path.exists(PUBLISHED_FILE):
        return set()
    with open(PUBLISHED_FILE, 'r', encoding='utf-8') as file:
        return set(line.strip() for line in file)

def save_published_article(link):
    """Save a new article link to the file."""
    with open(PUBLISHED_FILE, 'a', encoding='utf-8') as file:
        file.write(link + '\n')

def scrape_article(url):
    """Scrape the detailed content of a news article."""
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find the headline (English title)
        headline = soup.find('h1') or soup.find('h2')
        headline = headline.get_text(strip=True) if headline else "No headline found"

        # Find the main content
        body = None
        for class_name in ['content', 'article-body', 'story', 'post', 'entry-content']:
            body_tag = soup.find('div', class_=class_name)
            if body_tag:
                body = body_tag.get_text(strip=True)
                break
        if not body:
            paragraphs = soup.find_all('p')
            body = "\n".join([p.get_text(strip=True) for p in paragraphs]) if paragraphs else "No content found"

        return {'headline': headline, 'content': body}
    except Exception as e:
        print(f"Error scraping article: {e}")
        return None

def post_news_to_channel():
    """Fetch, scrape, summarize, and post news articles with images to the Telegram channel."""
    entries = fetch_rss_feed()
    if not entries:
        print("No entries found in the RSS feed.")
        return

    published_articles = read_published_articles()

    for entry in entries:
        link = entry.link

        # Skip if the article has already been posted
        if link in published_articles:
            print(f"Skipping already published article: {link}")
            continue

        # Scrape the article details
        article = scrape_article(link)
        if not article:
            print(f"Failed to scrape article: {link}")
            continue

        # Post to Telegram (simplified for brevity)
        send_message(f"🔴 {article['headline']}\n\n{article['content']}\n\n<a href='{html.escape(link)}'>Read more</a>")

        # Save the article link to avoid reposting
        save_published_article(link)

        time.sleep(2)

def send_message(text):
    """Send the message to the Telegram channel."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': CHANNEL_ID,
        'text': text,
        'parse_mode': 'HTML'
    }
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"Error sending message: {e}")

if __name__ == "__main__":
    post_news_to_channel()

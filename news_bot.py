import requests
import feedparser
import os
import html
import time
from bs4 import BeautifulSoup

# Fetch the secrets from environment variables
API_KEY = os.getenv('API_KEY')
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')

# CBC Canada News RSS Feed URL
RSS_FEED_URL = 'https://rss.cbc.ca/lineup/canada.xml'

# Gemini API endpoint
URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={API_KEY}"

# File to store published articles
PUBLISHED_FILE = "published_articles.txt"

def fetch_rss_feed():
    """Fetch the RSS feed and extract links."""
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(RSS_FEED_URL, headers=headers, timeout=10)
        response.raise_for_status()
        feed = feedparser.parse(response.text)
        return [entry.link for entry in feed.entries[:5]]  # Return the latest 5 links
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

        # Find the headline
        headline = None
        for tag in ['h1', 'h2']:
            headline_tag = soup.find(tag)
            if headline_tag:
                headline = headline_tag.get_text(strip=True)
                break
        if not headline:
            headline = "No headline found"

        # Find the main content
        body = None
        for class_name in ['content', 'article-body', 'story', 'post', 'entry-content']:
            body_tag = soup.find('div', class_=class_name)
            if body_tag:
                body = body_tag.get_text(strip=True)
                break
        if not body:
            paragraphs = soup.find_all('p')
            if paragraphs:
                body = "\n".join([p.get_text(strip=True) for p in paragraphs])
            else:
                body = "No content found"

        # Find the publication date
        publication_date = None
        time_tag = soup.find('time')
        if time_tag:
            publication_date = time_tag.get_text(strip=True)
        else:
            meta_date = soup.find('meta', {'property': 'article:published_time'})
            if meta_date and meta_date.get('content'):
                publication_date = meta_date.get('content')
            else:
                publication_date = "No publication date found"

        return {'headline': headline, 'content': body, 'date': publication_date}
    except Exception as e:
        print(f"Error scraping article: {e}")
        return None

def generate_summary(headline, content):
    """Send the title and content to Gemini API for summarization."""
    headers = {"Content-Type": "application/json"}
    prompt = f"""
    First read the following title and content:
    Title: {headline}
    Content: {content}
    
    Then, summarize them into a short Persian summary with a new title of your choosing. The summary should be the only output.
    """

    data = {
        "prompt": prompt,
        "temperature": 0.7,
        "top_p": 0.9,
        "candidate_count": 1,
        "max_output_tokens": 512
    }

    try:
        response = requests.post(URL, headers=headers, json=data)
        response.raise_for_status()
        return response.json()['candidates'][0]['output']
    except Exception as e:
        print(f"Error generating summary: {e}")
        return None

def send_message(text):
    """Send the summary to the Telegram channel."""
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

def post_news_to_channel():
    """Fetch, scrape, summarize, and post news articles to the Telegram channel."""
    links = fetch_rss_feed()
    if not links:
        print("No links found in the RSS feed.")
        return

    published_articles = read_published_articles()
    for link in links:
        if link in published_articles:
            print(f"Skipping already published article: {link}")
            continue

        article = scrape_article(link)
        if not article:
            print(f"Failed to scrape article: {link}")
            continue

        summary = generate_summary(article['headline'], article['content'])
        if not summary:
            print(f"Failed to generate summary for: {link}")
            continue

        message = f"<b>{html.escape(article['headline'])}</b>\n\n{html.escape(summary)}\n\n<a href='{html.escape(link)}'>Read more</a>"
        send_message(message)
        save_published_article(link)
        time.sleep(2)

if __name__ == "__main__":
    post_news_to_channel()

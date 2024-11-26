import requests
import feedparser
import os
import html
import time
from bs4 import BeautifulSoup
import shutil

# Embed the API keys directly here (replace with your keys)
API_KEY = os.getenv("API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

# Dictionary mapping feed URLs to their corresponding topics
RSS_FEEDS = {
    'https://www.cbc.ca/webfeed/rss/rss-topstories': 'topstories',
    'https://www.cbc.ca/webfeed/rss/rss-world': 'world',
    'https://www.cbc.ca/webfeed/rss/rss-canada': 'canada',
    'https://www.cbc.ca/webfeed/rss/rss-politics': 'politics',
    'https://www.cbc.ca/webfeed/rss/rss-business': 'business',
    'https://www.cbc.ca/webfeed/rss/rss-health': 'health',
    'https://www.cbc.ca/webfeed/rss/rss-arts': 'arts',
    'https://www.cbc.ca/webfeed/rss/rss-technology': 'technology',
    'https://www.cbc.ca/webfeed/rss/rss-Indigenous': 'indigenous',
    'https://www.cbc.ca/webfeed/rss/rss-sports': 'sports',
}

# Gemini API endpoint
URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={API_KEY}"

# File to store published articles
PUBLISHED_FILE = "published_articles.txt"

# Folder for saving images
IMAGE_FOLDER = "saved_images"

def fetch_rss_feed(feed_url):
    """Fetch the RSS feed from the given URL and extract all entries."""
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(feed_url, headers=headers, timeout=10)
        response.raise_for_status()
        feed = feedparser.parse(response.text)
        return feed.entries  # Return all entries
    except requests.exceptions.RequestException as e:
        print(f"Error fetching the RSS feed {feed_url}: {e}")
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

        headline = soup.find('h1') or soup.find('h2')
        headline = headline.get_text(strip=True) if headline else "No headline found"

        body = None
        for class_name in ['content', 'article-body', 'story', 'post', 'entry-content']:
            body_tag = soup.find('div', class_=class_name)
            if body_tag:
                body = body_tag.get_text(strip=True)
                break
        if not body:
            paragraphs = soup.find_all('p')
            body = "\n".join([p.get_text(strip=True) for p in paragraphs]) if paragraphs else "No content found"

        publication_date = None
        time_tag = soup.find('time')
        if time_tag:
            publication_date = time_tag.get_text(strip=True)
        else:
            meta_date = soup.find('meta', {'property': 'article:published_time'})
            publication_date = meta_date.get('content') if meta_date and meta_date.get('content') else "No publication date found"

        return {'headline': headline, 'content': body, 'date': publication_date}
    except Exception as e:
        print(f"Error scraping article: {e}")
        return None

def generate_summary(headline, content):
    """Send the title and content to Gemini API for summarization."""
    headers = {"Content-Type": "application/json"}
    # Adjusted prompt for click-baity title and hashtags
    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "Summarize the following story in Persian while keeping English names, terms, and entities unchanged. "
                            "Make the title click-baity to attract the reader's attention while staying relevant to the content. "
                            "At the end of the summary, add three hashtags that are relevant to the story in both English and Persian, separated by commas.\n\n"
                            f"Title: {headline}\n\n{content}"
                        )
                    }
                ]
            }
        ]
    }
    try:
        response = requests.post(URL, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        # Parse the response to extract title, summary, and hashtags
        persian_summary = result["candidates"][0]["content"]["parts"][0]["text"]
        lines = persian_summary.strip().split('\n')
        if len(lines) >= 3:
            cleaned_title = lines[0].strip()
            cleaned_summary = "\n".join(lines[1:-1]).strip()
            hashtags = lines[-1].strip()
        elif len(lines) == 2:
            cleaned_title, cleaned_summary = lines
            hashtags = ""
        else:
            cleaned_title = lines[0]
            cleaned_summary = ''
            hashtags = ''
        return cleaned_title.strip(), cleaned_summary.strip(), hashtags.strip()
    except requests.exceptions.RequestException as e:
        print(f"Error generating summary: {e}")
        return None, None, None

def extract_image_from_description(description):
    """Extract the image URL from the RSS description tag."""
    try:
        if not description:
            return None
        soup = BeautifulSoup(description, 'html.parser')
        img_tag = soup.find('img')
        if img_tag and 'src' in img_tag.attrs:
            return img_tag['src']
        return None
    except Exception as e:
        print(f"Error extracting image from description: {e}")
        return None

def download_image(image_url):
    """Download an image and save it locally."""
    try:
        if not os.path.exists(IMAGE_FOLDER):
            os.makedirs(IMAGE_FOLDER)
        filename = os.path.join(IMAGE_FOLDER, os.path.basename(image_url).split('?')[0])
        response = requests.get(image_url, headers={'User-Agent': 'Mozilla/5.0'}, stream=True, timeout=10)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type')
        if not content_type.startswith('image/'):
            print(f"URL does not contain an image: {image_url}")
            return None
        # Limit image size to 10 MB
        max_size = 10 * 1024 * 1024  # 10 MB
        total_size = 0
        with open(filename, 'wb') as img_file:
            for chunk in response.iter_content(1024):
                total_size += len(chunk)
                if total_size > max_size:
                    print(f"Image size exceeds 10 MB: {image_url}")
                    return None
                img_file.write(chunk)
        return filename
    except Exception as e:
        print(f"Error downloading image: {e}")
        return None

def send_message_with_local_image(image_path, caption):
    """Send an image from a local file to the Telegram channel."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    response = None
    try:
        with open(image_path, 'rb') as photo:
            payload = {
                'chat_id': CHANNEL_ID,
                'caption': caption,
                'parse_mode': 'HTML'
            }
            files = {'photo': photo}
            response = requests.post(url, data=payload, files=files)
            response.raise_for_status()
            return True
    except requests.exceptions.RequestException as e:
        print(f"Error sending message with local image: {e}")
        if response is not None and response.content:
            try:
                error_info = response.json()
                print(f"Telegram API error: {error_info}")
            except ValueError:
                print(f"Non-JSON response content: {response.content}")
        return False

def send_message_without_image(caption):
    """Send a message without an image to the Telegram channel."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    response = None
    try:
        payload = {
            'chat_id': CHANNEL_ID,
            'text': caption,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, data=payload)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error sending message without image: {e}")
        if response is not None and response.content:
            try:
                error_info = response.json()
                print(f"Telegram API error: {error_info}")
            except ValueError:
                print(f"Non-JSON response content: {response.content}")
        return False

def clear_image_folder():
    """Clear all images in the IMAGE_FOLDER directory without deleting the folder."""
    try:
        if os.path.exists(IMAGE_FOLDER):
            for filename in os.listdir(IMAGE_FOLDER):
                file_path = os.path.join(IMAGE_FOLDER, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)  # Remove each file in the folder
            print("DEBUG: Cleared the contents of the image folder.")
        else:
            print(f"DEBUG: Folder '{IMAGE_FOLDER}' does not exist, nothing to clear.")
    except Exception as e:
        print(f"Error clearing image folder: {e}")

def truncate_text(text, max_length):
    """Truncate text to a maximum length, adding ellipsis if truncated."""
    if len(text) > max_length:
        return text[:max_length - 3] + '...'
    else:
        return text

def process_feed(feed_url, topic):
    """Process a single RSS feed."""
    entries = fetch_rss_feed(feed_url)
    if not entries:
        return
    published_articles = read_published_articles()
    for entry in entries:
        link = entry.link
        if link in published_articles:
            continue
        article = scrape_article(link)
        if not article:
            continue
        # Generate summary, get title, summary, and hashtags
        persian_title, summary, hashtags = generate_summary(article['headline'], article['content'])
        if not persian_title or not summary:
            continue
        # Append topic-specific hashtag
        topic_hashtag = f"#{topic}"
        if hashtags:
            hashtags = f"{hashtags}, {topic_hashtag}"
        else:
            hashtags = topic_hashtag
        # Prepare the message
        escaped_title = html.escape(persian_title)
        escaped_summary = html.escape(summary)
        read_more_link = f"\n\n<a href='{link}'>بیشتر بخوانید</a>"
        formatted_summary = f"<b>🔴 {escaped_title}</b>\n\n{escaped_summary}{read_more_link}\n\n{hashtags}"
        # Determine the maximum length based on whether an image is present
        description = getattr(entry, "description", None)
        image_url = extract_image_from_description(description)
        if image_url:
            max_length = 1024
        else:
            max_length = 4096
        # Truncate if necessary
        if len(formatted_summary) > max_length:
            title_length = len(f"<b>🔴 {escaped_title}</b>\n\n")
            link_length = len(read_more_link)
            hashtag_length = len(hashtags) + 2  # Including the new line
            available_summary_length = max_length - title_length - link_length - hashtag_length
            truncated_summary = truncate_text(escaped_summary, available_summary_length)
            formatted_summary = f"<b>🔴 {escaped_title}</b>\n\n{truncated_summary}{read_more_link}\n\n{hashtags}"
        success = False
        if image_url:
            image_path = download_image(image_url)
            if image_path:
                success = send_message_with_local_image(image_path, formatted_summary)
                if not success:
                    print("Failed to send image with message, trying without image.")
                    success = send_message_without_image(formatted_summary)
            else:
                print("Failed to download image, sending message without image.")
                success = send_message_without_image(formatted_summary)
        else:
            print("No image available for this article.")
            success = send_message_without_image(formatted_summary)
        if success:
            save_published_article(link)
        else:
            print("Failed to send message, not saving link.")
        time.sleep(2)
    clear_image_folder()

def post_news_to_channel():
    """Fetch, scrape, summarize, and post news articles from multiple RSS feeds."""
    for feed_url, topic in RSS_FEEDS.items():
        try:
            print(f"Processing feed: {feed_url} with topic: {topic}")
            process_feed(feed_url, topic)
        except Exception as e:
            print(f"Error processing feed {feed_url}: {e}")

if __name__ == "__main__":
    post_news_to_channel()

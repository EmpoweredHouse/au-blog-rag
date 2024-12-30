import logging
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from slack_sdk import WebClient
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# https://slack-rag-bot-610678049636.us-central1.run.app/slack/events

class SlackBot:
    """
    SlackBot class for handling Slack messages, interacting with a RAG system, and responding using Slack Block Kit.
    """
    def __init__(self, rag_system, slack_bot_token, signing_secret):
        """
        Initialize the SlackBot with a RAG system, Slack bot token, and signing secret.

        :param rag_system: The QueryHandler object for answering user queries.
        :param slack_bot_token: The Slack bot token for authentication.
        :param signing_secret: The Slack signing secret for verifying requests.
        """
        self.rag_system = rag_system 
        self.app = App(token=slack_bot_token, signing_secret=signing_secret)
        self.flask_app = Flask(__name__)
        self.handler = SlackRequestHandler(self.app)

        # Register Slack events
        self.register_event_listeners()

    def register_event_listeners(self):
        """Register event listeners for the Slack app."""

        @self.app.event("message")
        def handle_direct_message(body, say, ack, client: WebClient):
            # Acknowledge the event immediately
            ack()

            """Main entry point for handling Slack messages."""
            try:
                event = body.get("event", {})
                user_id = event.get("user")
                channel_id = event.get("channel")

                if not self._is_valid_event(event):
                    return

                channel_id = event['channel']
                text = event.get('text', '').strip()

                # Send typing indicator
                user_id = event.get('user')
                self._send_typing_placeholder(client, channel_id, user_id)

                # Process the user's question and generate a response
                response = self._generate_response(text)

                # Send the response back to the user
                self._send_response(client, channel_id, response)
                
            except ValueError as ve:
                logger.error(f"Validation error: {ve}")
                say(str(ve))
            except Exception as e:
                logger.error(f"Unexpected error while processing message: {e}")
                say("An unexpected error occurred. Please try again later.")

    def start(self):
        """Start the Flask server."""
        @self.flask_app.route("/slack/events", methods=["POST"])
        def slack_events():
            return self.handler.handle(request)

        self.flask_app.run(port=3000)


    @staticmethod
    def _is_valid_event(event):
        """Validate the Slack event."""
        if event.get('channel_type') not in ['im', 'group']:
            return False
        if event.get('bot_id'):  # Ignore bot messages
            return False
        if not event.get('text', '').strip():
            raise ValueError("Message text is empty.")
        return True

    @staticmethod
    def _send_typing_placeholder(client, channel_id, user):
        """Send a placeholder 'Thinking...' message."""
        try:
            return client.chat_postMessage(
                channel=channel_id,
                text=f"Hi <@{user}>, I'm starting to process your request...",
                user=user
            )
        except Exception as e:
            logger.error(f"Failed to send 'Thinking...' placeholder: {e}")
            raise ValueError("Unable to send 'Thinking...' placeholder.")

    def _generate_response(self, text):
        """
        Generate a response to the user's question using the RAG system.

        :param text: The user's query text.
        :return: A dictionary containing Slack Block Kit message blocks or a plain text message.
        """
        results = self.rag_system.get_answer(text, filter_false=True, analysis_model="gpt-4o")
        if not results:
            return "No relevant information found for your query."
        return {"blocks": self._build_slack_message_blocks(results)}

    @staticmethod
    def _send_response(client, channel_id, response):
        """
        Send the generated response back to the Slack channel.

        :param client: The Slack WebClient for API interactions.
        :param channel_id: The ID of the Slack channel where the response will be sent.
        :param response: The response to send, either as plain text or Block Kit message blocks.
        :raises ValueError: If sending the response message fails.
        """
        try:
            if isinstance(response, dict) and "blocks" in response:
                client.chat_postMessage(
                    channel=channel_id,
                    blocks=response["blocks"],
                    unfurl_links=False  # Disable link unfurling
                )
            else:
                client.chat_postMessage(
                    channel=channel_id,
                    text=response,
                    unfurl_links=False  # Disable link unfurling
                )
        except Exception as e:
            logger.error(f"Failed to send response message: {e}")
            raise ValueError("Unable to send the Slack response.")

    @staticmethod
    def _build_slack_message_blocks(results):
        """
        Build Slack Block Kit message blocks from query results.

        :param results: List of dictionaries containing the following fields:
            - url: The URL of the article.
            - score: The retriever score of the article.
            - decision: The decision about article relevance.
            - summary: A brief summary of the article.
            - response: The response to the user's question, based on the article content.
        :return: A list of Slack Block Kit message blocks.
        """
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Analysis Results:*"
                }
            },
            {"type": "divider"}
        ]

        for result in results[:20]:
            url = result.get('url', 'URL not available')
            # decision = result.get('decision', 'Decision not available')
            summary = result.get('summary', 'Summary not available')
            response = result.get('response', 'Response not available')

            result_text = (
                f"{url}\n\n"
                # f"• *Decision:* `{decision}`\n"
                f"• *Summary:* {summary}\n\n"
                f"• *Hint:* {response}"
            )

            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": result_text
                    }
                }
            )
            blocks.append({"type": "divider"})
        return blocks

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from .models import ChatRoom, ChatMessage

User = get_user_model()


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Extract room ID from URL
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'chat_room_{self.room_id}'
        self.user = self.scope['user']
        
        # Check if user has permission to access this room
        if not await self.user_can_access_room():
            await self.close()
            return
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
    
    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type', 'message')
            
            if message_type == 'message':
                message = text_data_json.get('message', '')
                if message.strip():
                    # Save message to database
                    chat_message = await self.save_message(message)
                    
                    # Send message to room group
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'chat_message',
                            'message': message,
                            'author_email': self.user.email,
                            'author_avatar': self.user.avatar.url if self.user.avatar else '',
                            'created_at': chat_message.created_at.strftime('%H:%M'),
                            'is_staff': self.user.is_staff
                        }
                    )
            
            elif message_type == 'typing':
                # Handle typing indicators
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'typing_indicator',
                        'user_email': self.user.email,
                        'is_typing': text_data_json.get('is_typing', False)
                    }
                )
                
        except json.JSONDecodeError:
            pass
    
    async def chat_message(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': event['message'],
            'author_email': event['author_email'],
            'author_avatar': event['author_avatar'],
            'created_at': event['created_at'],
            'is_staff': event['is_staff']
        }))
    
    async def typing_indicator(self, event):
        # Don't send typing indicator to the person who is typing
        if event['user_email'] != self.user.email:
            await self.send(text_data=json.dumps({
                'type': 'typing',
                'user_email': event['user_email'],
                'is_typing': event['is_typing']
            }))
    
    @database_sync_to_async
    def user_can_access_room(self):
        """Check if user can access the room"""
        try:
            room = ChatRoom.objects.get(id=self.room_id)
            # User can access their own room or staff can access any room
            return room.user == self.user or self.user.is_staff
        except ChatRoom.DoesNotExist:
            return False
    
    @database_sync_to_async
    def save_message(self, message):
        """Save message to database"""
        try:
            room = ChatRoom.objects.get(id=self.room_id)
            chat_message = ChatMessage.objects.create(
                room=room,
                author=self.user,
                content=message
            )
            return chat_message
        except ChatRoom.DoesNotExist:
            return None
from sqlalchemy import Column, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, relationship, Session
from flask import (
    Flask,
    Response,
    request
)


import json
import requests


from dataclasses import dataclass
from enum import Enum
from typing import Optional, Union
from collections import defaultdict

Base = declarative_base()

DATABASE_NAME = "sqlite:///database.db"
TOKEN = "<telegram-token>"
WE_BOT_UID = "<we-uid>"
SERVER_URL = "<server-url>"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    state = Column(String, nullable=False)

    links = relationship("Link", back_populates="user",
                         cascade="all, delete-orphan")
    chats = relationship("Chat", back_populates="user",
                         cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, user_id={self.user_id!r}, state={self.state!r})"


class Link(Base):
    __tablename__ = "links"

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey("chats.chat_id"), nullable=False)
    we_id = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)

    user = relationship("User", back_populates="links")
    chat = relationship("Chat", back_populates="links")

    def __repr__(self) -> str:
        return f"Link(id={self.id!r}, tg_id={self.chat_id!r}, we_id={self.we_id!r}), user_id={self.user_id!r}"


class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer)
    username = Column(String)
    title = Column(String)
    type = Column(String)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)

    user = relationship("User", back_populates="chats")
    links = relationship("Link", back_populates="chat")

    def __repr__(self) -> str:
        return f"Chat(chat_id={self.chat_id!r}, title={self.title!r}, type={self.type!r})"


class Cobalt:
    class Message:

        class Type(Enum):
            Command = 0
            Message = 1
            ChangeStatusInChat = 2
            ChannelPost = 3

        @dataclass
        class Status:
            new: Optional[str] = None
            old: Optional[str] = None

        @dataclass
        class User:
            id: Optional[str] = None
            is_bot: Optional[bool] = None
            first_name: Optional[str] = None
            last_name: Optional[str] = None
            username: Optional[str] = None
            language_code: Optional[str] = None
            title: Optional[str] = None
            type: Optional[str] = None

        @dataclass
        class Chat:
            id: Optional[str] = None
            title: Optional[str] = None
            type: Optional[str] = None
            first_name: Optional[str] = None
            last_name: Optional[str] = None
            username: Optional[str] = None
            all_members_are_administrators: Optional[bool] = None

            types_in_fa = defaultdict(
                lambda: "",
                {
                    "private": "خصوصی",
                    "group": "گروه",
                    "supergroup": "سوپرگروه",
                    "channel": "کانال"
                }
            )

            @property
            def type_fa(self) -> str:
                return self.types_in_fa[self.type]

        def __init__(self, message: dict):
            self.update_id: int = message['update_id']

            message_key = ""
            if "message" in message:
                message_key = "message"
                self.type = Cobalt.Message.Type.Message
            elif "my_chat_member" in message:
                message_key = "my_chat_member"
                self.type = Cobalt.Message.Type.ChangeStatusInChat
            elif "channel_post" in message:
                message_key = "channel_post"
                self.type = Cobalt.Message.Type.ChannelPost

            if "message_id" in message[message_key]:
                self.message_id = message[message_key]['message_id']

            if self.type == Cobalt.Message.Type.ChannelPost:
                user_key = "sender_chat"
            else:
                user_key = "from"

            self.user = Cobalt.Message.User(**message[message_key][user_key])
            self.chat = Cobalt.Message.Chat(**message[message_key]['chat'])
            self.date = message[message_key]['date']

            self._is_command = (
                'message' in message
                and 'entities' in message['message']
                and bool(tuple(filter(lambda x: 'type' in x and x['type'] == 'bot_command', message['message']['entities'])))
            )

            if self._is_command:
                self.type = Cobalt.Message.Type.Command

            if "text" in message[message_key]:
                self.text = message[message_key]['text']
                
            if message_key == "my_chat_member":
                self.status = Cobalt.Message.Status(
                    message[message_key]['new_chat_member']['status'], message[message_key]['old_chat_member']['status'])
                chat_member = message["my_chat_member"]['new_chat_member']

                self.privileges = list(
                    filter(lambda x: type(chat_member[x]) is bool, chat_member))

        def is_command(self, cmd_name: Optional[str] = None) -> bool:
            return self.type == Cobalt.Message.Type.Command and (cmd_name is None or self.text == '/' + cmd_name.lstrip('/'))

    class WeBot:

        chat_type = {'2': "GROUP", '3': "CHANNEL"}

        def __init__(self, we_bot_uid: str):
            self.we_bot_uid = we_bot_uid
            self.url = f"https://api.wemessenger.ir/v2/{self.we_bot_uid}/sendMessage"
            self.headers = {
                'Content-Type': 'application/json'
            }

        def send_message(self, chat_id: str, text: str) -> bytes:

            chat_data = chat_id.split(':')
            data = json.dumps({
                "to": {
                    "category": Cobalt.WeBot.chat_type[chat_data[0]],
                    "node": chat_data[1],
                    "session_id": "*"
                },
                "text": {
                    "text": text
                }
            })

            response = requests.request(
                "POST", self.url, headers=self.headers, data=data)

            return response.text.encode('utf8')

    def __init__(self, token: str, server_url: Optional[str] = None):
        self.token = token
        self.server_url = server_url

    def run(self) -> Optional[str]:
        if self.server_url is not None:
            engine = create_engine(DATABASE_NAME, echo=False, future=True)
            Base.metadata.create_all(engine)
            return f"""<h1>Welcome!</h1>webhook: {self.set_webhook(self.server_url)}<hr>commands: {self.set_commands([
                {"command": "add_link", "description": "افزودن لینک"}
            ])},"""

    @property
    def message(self) -> Message:
        return Cobalt.Message(request.get_json())

    def set_webhook(self, server_url: str) -> dict:
        return requests.post(f"https://api.telegram.org/bot{self.token}/setWebhook?url={server_url}").json()

    def set_commands(self, commands: list[dict[str, str]]) -> dict:

        return requests.post(f"https://api.telegram.org/bot{self.token}/setMyCommands?commands={json.dumps(commands)}").json()

    def send_message(self, text: str, to: Optional[str] = None) -> dict:

        url = f'https://api.telegram.org/bot{self.token}/sendMessage'
        json = {
            'chat_id': self.message.user.id if to is None else to,
            'text': text
        }
        return requests.post(url, json=json).json()


class Database:
    def __init__(self, database_name: str):
        self.engine = create_engine(database_name, echo=False, future=True)

    def add_chat(self, message: Cobalt.Message) -> bool:
        with Session(self.engine) as session:
            chat = session.query(Chat).filter_by(chat_id="11").first()
            if chat is not None:
                return False

            session.add(
                Chat(
                    chat_id=message.chat.id,
                    username=message.chat.username,
                    title=message.chat.title,
                    type=message.chat.type,
                    user_id=message.user.id
                )
            )
            session.commit()
            return True

    def remove_chat(self, message: Cobalt.Message) -> bool:
        with Session(self.engine) as session:
            session.query(Link).filter_by(chat_id=message.chat.id).delete()
            session.query(Chat).filter_by(chat_id=message.chat.id).delete()
            session.commit()
            return True

    def get_user_chats(self, user_id: str) -> str:
        with Session(self.engine) as session:
            user = session.query(Chat).filter_by(user_id=user_id).all()
            if user is None:
                return ""
            data = session.query(Chat).with_entities(Chat.title).all()
            return "\n".join(map(lambda y: f"{y[0]}. {y[1]}", enumerate(map(lambda x: x[0], data), 1)))

    def set_user_state(self, user_id: str, state: str) -> bool:
        with Session(self.engine) as session:
            user = session.query(User).filter_by(user_id=user_id).first()
            if user is None:
                session.add(User(user_id=user_id, state=state))
            else:
                user.state = state
            session.commit()
            return True

    def get_user_state(self, user_id: str) -> str:
        with Session(self.engine) as session:
            user = session.query(User).filter_by(user_id=user_id).first()
            if user is None:
                return ""
            return user.state

    def add_link(self, user_id: Optional[str], title: str) -> bool:
        with Session(self.engine) as session:
            chat = (
                session
                .query(Chat)
                .where((Chat.user_id == user_id) | (Chat.username == title if title[0] == "@" else Chat.title == title))
                .first()
            )
            if chat is None:
                return False
            session.add(Link(chat_id=chat.chat_id, user_id=user_id))
            session.commit()
            return True

    def add_we_id_to_link(self, user_id: Optional[str], we_id: str) -> bool:
        with Session(self.engine) as session:
            link = session.query(Link).where((Link.user_id == user_id) & (
                Link.we_id == None)).order_by(Link.id.desc()).first()
            if link is None:
                return False
            link.we_id = we_id
            session.commit()
            return True

    def get_we_clients(self, chat_id: Optional[int]) -> Union[filter, list]:
        with Session(self.engine) as session:
            links = session.query(Link).filter_by(chat_id=chat_id).all()
            if links is None:
                return []
            return filter(lambda x: x is not None, map(lambda x: x.we_id, links))


app = Flask(__name__)


@app.route('/', methods=['POST', 'GET'])
def index():

    if request.method == 'GET':
        return Cobalt(token=TOKEN, server_url=SERVER_URL).run()

    else:
        bot = Cobalt(token=TOKEN)
        db = Database(DATABASE_NAME)
        if bot.message.chat.type == "private" and bot.message.chat.id == bot.message.user.id:  # private chat
            if bot.message.is_command('start'):
                bot.send_message(
                    text="به ربات اتصال تلگرام به وی خوش آمدید. این ربات به منظور ایجاد یک ارتباط یک طرفه تلگرام با پیام‌رسان وی می‌باشد. "
                )
                db.set_user_state(bot.message.user.id, "start")

            elif bot.message.is_command('add_link'):
                bot.send_message(
                    "شناسه یا عنوان گروه یا کانال را وارد نمایید. توجه شود که شناسه لزوما باید با علامت @ آغاز گردد، در غیر اینصورت بصورت عنوان در نظر گرفته خواهد شد."
                )
                bot.send_message(db.get_user_chats(bot.message.user.id))
                db.set_user_state(bot.message.user.id, "add_link")
            elif db.get_user_state(bot.message.user.id) == "add_link":
                if db.add_link(bot.message.user.id, bot.message.text):
                    db.set_user_state(bot.message.user.id, "add_link_we_part")
                    bot.send_message(
                        "اکنون شناسه مربوط به کانال یا گروه پیام‌رسان وی را وارد نمایید")
                else:
                    bot.send_message(
                        "کانال یا گروهی با چنین عنوان یا شناسه‌ایی وجود ندارد")
            elif db.get_user_state(bot.message.user.id) == "add_link_we_part":
                if db.add_we_id_to_link(bot.message.user.id, bot.message.text):
                    bot.send_message("لینک با موفقیت اضافه شد")
                db.set_user_state(bot.message.user.id, "start")
        else:
            if bot.message.type == Cobalt.Message.Type.ChangeStatusInChat:

                if bot.message.status.new in ['administrator']:
                    if db.add_chat(bot.message):
                        bot.send_message(
                            text=f"ربات به {bot.message.chat.type_fa} {bot.message.chat.title} اضافه شد"
                        )
                    else:
                        bot.send_message(
                            text=f"ربات در {bot.message.chat.type_fa} {bot.message.chat.title} عضو می‌باشد"
                        )
                elif bot.message.status.new in ['left', 'kicked', 'member']:
                    if db.remove_chat(bot.message):
                        bot.send_message(
                            text=f"ربات از {bot.message.chat.type_fa} {bot.message.chat.title} حذف شد"
                        )
                    else:
                        bot.send_message(
                            text=f"ربات در {bot.message.chat.type_fa} {bot.message.chat.title} عضو نمی‌باشد"
                        )
            else:
                we_bot = Cobalt.WeBot(WE_BOT_UID)
                for we_id in db.get_we_clients(bot.message.chat.id):
                    we_bot.send_message(we_id, bot.message.text)

        return Response('OK', status=200)


app.run(debug=True)

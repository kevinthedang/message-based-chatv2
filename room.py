from curses import erasechar
from email import message
import pika
import json
import pika.exceptions
import logging
from users import *
from constants import *
from datetime import date, datetime
from pymongo import MongoClient, ReturnDocument
from collections import deque
from constants import *

MONGO_DB = 'detest'
#MONGO_DB = 'chatroom'
logging.basicConfig(filename='chatroom.log', level=logging.DEBUG, filemode='w', format = LOG_FORMAT)

class MessageProperties():
    """ Class for holding the properties of a message: type, sent_to, sent_from, rec_time, send_time
        NOTE: The sequence number is defaulted to -1
        TODO: make getters for all of the private variables
    """
    def __init__(self, room_name: str, to_user: str, from_user: str, mess_type: int, sequence_num: int = -1, sent_time: datetime = datetime.now(), rec_time: datetime = datetime.now()) -> None:
        self.__mess_type = mess_type
        self.__room_name = room_name
        self.__to_user = to_user
        self.__from_user = from_user
        self.__sent_time = sent_time
        self.__rec_time = rec_time     
        self.__sequence_num = sequence_num

    def to_dict(self):
        return {'room_name': self.__room_name, 
            'mess_type': self.__mess_type,
            'to_user': self.__to_user, 
            'from_user': self.__from_user,
            'sent_time': self.__sent_time,
            'rec_time': self.__rec_time, 
            'sequence_num': self.__sequence_num,
        } 

    # the following properties are to get functions to get message properties
    @property
    def message_type(self):
        return self.__mess_type

    @property
    def room_name(self):
        return self.__room_name

    @property
    def to_user(self):
        return self.__to_user

    @property
    def from_user(self):
        return self.__from_user

    @property
    def sent_time(self):
        return self.__sent_time

    @property
    def rec_time(self):
        return self.__rec_time

    @property
    def sequence_number(self):
        return self.__sequence_num

    @sequence_number.setter
    def sequence_number(self, new_value: int):
        self.__sequence_num = new_value

    def __str__(self):
        return str(self.to_dict())

class ChatMessage():
    """ Class for holding individual messages in a chat thread/queue. Each message a message, rabbitmq properties, sequence number, timestamp and type
        NOTE: message id is autogenerated by mongodb
    """
    def __init__(self, message: str, mess_id = None, mess_props: MessageProperties = None) -> None:
        self.__message = message
        self.__mess_props = mess_props
        self.__mess_id = mess_id
        self.__dirty = True

    # the following 4 properties are set so information about a ChatMessage instance can be obtained
    @property
    def message(self):
        return self.__message

    @property
    def message_properties(self):
        return self.__mess_props
    
    @property
    def dirty(self):
        return self.__dirty

    @property
    def message_id(self):
        return self.__mess_id

    @dirty.setter
    def dirty(self, new_value: bool):
        self.__dirty = new_value

    def to_dict(self):
        mess_props_dict = self.mess_props.to_dict()
        return {'message': self.message, 'mess_props': mess_props_dict}

    def __str__(self):
        return f'Chat Message: {self.message} - message props: {self.mess_props}'

class ChatRoom(deque):
    """ We reuse the constructor for creating new or grabbing an existing instance. If owner_alias is empty and user_alias is not, 
            this is assuming an existing instance. The opposite (owner_alias set and user_alias empty) means we're creating new
            members is always optional, and room_type is only relevant if we're creating new.
    """
    def __init__(self, room_name: str, member_list: list = None, owner_alias: str = "", room_type: int = ROOM_TYPE_PRIVATE, create_new: bool = False) -> None:
        super(ChatRoom, self).__init__()
        self.__room_name = room_name
        self.__user_list = UserList()
        self.__dirty = False
        self.__owner_alias = owner_alias
        # Set up mongo - client, db, collection, sequence_collection
        self.__mongo_client = MongoClient(host = MONGO_DB_HOST, port = MONGO_DB_PORT, username = MONGO_DB_USER, password = MONGO_DB_PASS, authSource = MONGO_DB_AUTH_SOURCE, authMechanism = MONGO_DB_AUTH_MECHANISM)
        self.__mongo_db = self.__mongo_client.detest
        self.__mongo_collection = self.__mongo_db.get_collection(self.__room_name) 
        self.__mongo_seq_collection = self.__mongo_db.get_collection("sequence")
        if self.__mongo_collection is None:
            self.__mongo_collection = self.__mongo_db.create_collection(self.__room_name)
        # Restore from mongo if possible, if not (or we're creating new) then setup ChatRoom properties
        if create_new is True or self.restore() is False:
            self.__create_time = datetime.now()
            self.__modify_time = datetime.now()
            self.__room_type = room_type
            if member_list is not None:
                self.__member_list = member_list
                if owner_alias not in member_list:
                    member_list.append(owner_alias)
            else:
                self.__member_list = list()
                self.__member_list.append(owner_alias)
            self.__dirty = True

    # property to get the name of a room
    @property
    def room_name(self):
        return self.__room_name

    # property to get the list of users for a room
    @property
    def room_user_list(self):
        return self.__user_list

    # property to get the members list for a room
    @property
    def member_list(self):
        return self.__member_list

    # property to get the owner_alias of the 
    @property
    def owner_alias(self):
        return self.__owner_alias

    # property to get the length of the deque
    @property
    def num_messages(self):
        return len(self)

    # property to get the type of the room
    @property
    def room_type(self):
        return self.__room_type

    # property to get if the room is dirty
    @property
    def dirty(self):
        return self.__dirty

    def __get_next_sequence_num(self):
        """ This is the method that you need for managing the sequence. Note that there is a separate collection for just this one document
        """
        sequence_num = self.__mongo_seq_collection.find_one_and_update(
                                                        {'_id': 'userid'},
                                                        {'$inc': {self.__room_name: 1}},
                                                        projection={self.__room_name: True, '_id': False},
                                                        upsert=True,
                                                        return_document=ReturnDocument.AFTER)
        return sequence_num

    #Overriding the queue type put and get operations to add type hints for the ChatMessage type
    def put(self, message: ChatMessage = None) -> None:
        ''' This method will put the current message to the left side of the deque
            TODO: put the message on the left using appendLeft() method
        '''
        logging.info(f'Caliing the put() method with current message being {message} appending to the left of the deque.')
        if message is not None:
            super().appendleft(message)
            logging.info(f'{message} was appended to the left of the queue.')

    # overriding parent and setting block to false so we don't wait for messages if there are none
    def get(self) -> ChatMessage:
        ''' This method will take a ChatMessage from the right side of the deque.
            NOTE: the method pop() to take a value from the right of the deque
        '''
        try:
            message_right = super()[-1]
        except:
            logging.debug(f'There is no message in the deque for room {self.__room_name}')
            return None
        else:
            logging.debug(f'Message {message} was found on the deque.')
            return message_right

    def find_message(self, message_text: str) -> ChatMessage:
        ''' Traverse through the deque of the Chatroom and find the ChatMessage 
                with the message_text input from the user.
            TODO: Understand how the deque works and how to traverse the deque.
            NOTE: To traverse through the deque, we can use list(self) as an iterable to find the message
            NOTE: an example would be (for current_message in list(self))
        '''
        for current_message in list(self):
            if current_message.message == message_text:
                logging.debug(f'found {message_text} in deque.')
                return current_message
        logging.debug(f'{message_text} was not found in the deque.')
        return None
            
    def get_messages(self, user_alias: str, num_messages: int = GET_ALL_MESSAGES, return_objects: bool = True):
        ''' This method will get num_messages from the deque and get their text, objects and a total count of the messages
            NOTE: total # of messages seems to just be num messages, but if getting all then just return the length of the list
            NOTE: indecies 0 and 1 is to access the values in the tuple for the objects and the number of objects
            NOTE: If room_type is public, the user may get messages from the chat
        '''
        # return message texts, full message objects, and total # of messages
        if user_alias not in self.__member_list and self.__room_type is ROOM_TYPE_PRIVATE:
            logging.warning(f'User with alias {user_alias} is not a member of {self.__room_name}.')
            return [], [], 0
        if return_objects is True:
            logging.debug('Returning messages with the message objects.')
            message_objects = self.__get_message_objects(num_messages = num_messages)
            if num_messages == GET_ALL_MESSAGES:
                return [current_message.message for current_message in list(self)], message_objects[0], message_objects[1]
            else:
                message_texts = list()
                for current_message_index in range(RIGHT_SIDE_OF_DEQUE, RIGHT_SIDE_OF_DEQUE - num_messages, RANGE_STEP):
                    message_texts.append(super()[current_message_index].message)
                return message_texts, message_objects[0], message_objects[1]
        else:
            logging.debug('Returning messages without the message objects.')
            if num_messages == GET_ALL_MESSAGES:
                return [current_message.message for current_message in list(self)], len(self)
            else:
                message_texts = list()
                for current_message_index in range(RIGHT_SIDE_OF_DEQUE, RIGHT_SIDE_OF_DEQUE - num_messages, RANGE_STEP):
                    message_texts.append(super()[current_message_index].message)
                return message_texts, len(message_texts)

    def __get_message_objects(self, num_messages: int = GET_ALL_MESSAGES):
        ''' This is a helper method to get the actual message objects rather than just the message from the object
        '''
        logging.info(f'Attempting to get message objects in {self.__room_name}.')
        if num_messages == GET_ALL_MESSAGES:
            logging.debug('Returning all message objects in the deque.')
            return list(self), len(self)
        message_objects = list()
        for current_message_object in range(RIGHT_SIDE_OF_DEQUE, RIGHT_SIDE_OF_DEQUE - num_messages, RANGE_STEP):
            message_objects.append(super()[current_message_object])
        logging.debug(f'Returning {num_messages} message objects from the deque.')
        return message_objects, len(message_objects)

    def send_message(self, message: str, from_alias: str, mess_props: MessageProperties = None) -> bool:
        ''' This method will send a message to the ChatRoom instance
            NOTE: we are assuming that message is not None or empty
            NOTE: we most likely will need to utilize the put function to put the message on the queue
            NOTE: we also need to create an instance of ChatMessage to put on the queue
            NOTE: should we persist after putting the message on the deque.
        '''
        logging.info(f'Attempting to send {message} with the alias {from_alias}.')
        if from_alias in self.__member_list or self.__room_type == ROOM_TYPE_PUBLIC:
            logging.debug(f'{from_alias} was granted access to {self.__room_name} to send a message.')
            if mess_props is not None:
                new_message = ChatMessage(message = message, mess_props = mess_props)
                self.put(new_message)
                logging.debug(f'New ChatMessage created with message {message} and placed in the deque.')
                self.persist()
                return True
            else:
                logging.warning(f'No message properties given, cannot generate to_user for message properties. Failed to send message.')
                return False
        else:
            logging.debug(f'Alias {from_alias} is not a member of the private chat room {self.__room_name}.')
            return False

    def restore(self) -> bool:
        ''' This method will restore the metadata and the messages that a certain ChatRoom instance needs
            NOTE: a ChatRoom will contain it's own collection, if we are creating a new collection, we don't
                    need to restore
        '''
        logging.info('Beginning the restore process.')
        room_metadata = self.__mongo_collection.find_one({ 'room_name' : self.__room_name })
        if room_metadata is None:
            logging.debug(f'Room name {self.__room_name} was not found in the collections.')
            return False
        self.__room_name = room_metadata['room_name']
        self.__owner_alias = room_metadata['owner_alias']
        self.__room_type = room_metadata['room_type']
        self.__member_list = room_metadata['member_list']
        self.__create_time = room_metadata['create_time']
        self.__modify_time = room_metadata['modify_time']
        for current_message in self.__mongo_collection.find({'message': {'$exists': 'true'}}):
            message_properties = MessageProperties(room_name = current_message['mess_props']['room_name'],
                                                    to_user = current_message['mess_props']['to_user'],
                                                    from_user = current_message['mess_props']['from_user'],
                                                    mess_type = current_message['mess_props']['mess_type'],
                                                    sequence_num = current_message['mess_props']['sequence_num'],
                                                    sent_time = current_message['mess_props']['sent_time'],
                                                    rec_time = current_message['mess_props']['rec_time'])
            new_message = ChatMessage(message = current_message['message'], mess_id = current_message['_id'], mess_props = message_properties)
            self.put(message = new_message)
            logging.debug('Message', current_message['message'], 'was placed onto the deque.')
        logging.info('All messages restored to the deque.')
        return True

    def persist(self):
        ''' This method will maintain the data inside of a ChatRoom instance:  
                - The metadata
                - The messages in the room.
            NOTE: we want to iterate through the deque
            TODO: understand how the sequence number is assigned
        '''
        logging.info(f'Beginning the persistence process for a chat room: {self.__room_name}.')
        if self.__mongo_collection.find_one({ 'room_name': self.__room_name }) is None:
            self.__room_id = self.__mongo_collection.insert_one({'room_name':self.__room_name,
                                                                'owner_alias': self.__owner_alias,
                                                                'room_type': self.__room_type,
                                                                'member_list': self.__member_list,
                                                                'create_time': self.__create_time,
                                                                'modify_time': self.__modify_time}) # metadata here
        else:
            if self.__dirty == True:
                self.__mongo_collection.replace_one({'room_name':self.__room_name,
                                                    'owner_alias': self.__owner_alias,
                                                    'room_type': self.__room_type,
                                                    'member_list': self.__member_list,
                                                    'create_time': self.__create_time,
                                                    'modify_time': self.__modify_time},
                                                    upsert = True) # metadata here and upsert = True to update the room metadata
        self.__dirty = False
        # put messages in the collection now
        for current_message in list(self):
            if current_message.dirty == True:
                if current_message.message_id is None or self.__mongo_collection.find_one({ '_id' : current_message.message_id }) is None:
                    current_message.message_properties.sequence_number = self.__get_next_sequence_num()
                    serialized = current_message.to_dict()
                    self.__mongo_collection.insert_one(serialized)
                    current_message.dirty = False


class RoomList():
    """ This is the RoomList class instance that will handle a list of ChatRooms and obtaining them.
        NOTE: no need to have properties as this will be the main handler of all other class instances.
        TODO: complete this class by writing its functions.
        TODO: check out the data model to see what names should be
    """
    def __init__(self, room_list_name: str = DEFAULT_ROOM_LIST_NAME) -> None:
        """ Try to restore from mongo and establish variables for the room list
            TODO: RoomList takes a name, set the name
            TODO: inherit a list, or create an internal variable for a list of rooms
            TODO: restore the mongoDB collection
            NOTE: restore will handle putting the rooms into the room_list
        """
        self.__room_list_name = room_list_name
        self.__room_list = list()
        self.__user_list = UserList()
        # Set up mongo - client, db, collection
        self.__mongo_client = MongoClient(host = MONGO_DB_HOST, port = MONGO_DB_PORT, username = MONGO_DB_USER, password = MONGO_DB_PASS, authSource = MONGO_DB_AUTH_SOURCE, authMechanism = MONGO_DB_AUTH_MECHANISM)
        self.__mongo_db = self.__mongo_client.detest
        self.__mongo_collection = self.__mongo_db.get_collection(room_list_name)
        if self.__mongo_collection is None:
            self.__mongo_collection = self.__mongo_db.create_collection(room_list_name)
        # Restore from mongo if possible, if not (or we're creating new) then setup properties
        if self.__restore() is not True:
            self.__room_list_create = datetime.now()
            self.__room_list_modify = datetime.now()
            self.__dirty = True

    def create(self, room_name: str, owner_alias: str, member_list: list = None, room_type: int = ROOM_TYPE_PRIVATE) -> ChatRoom:
        ''' This method will create a new ChatRoom given that the room_name is not already taken for the collection.
            NOTE: This can just be a checker for the chatroom name existing in the list when restored or if it's in the collection
            NOTE: Maybe check with the collection as it is possible for all names to not be in the list and removed, due to the option for removal
            TODO: it may not be needed to recreated an already existing Chatroom (through restore() method).
        '''
        logging.info(f'Attempting to create a ChatRoom instance with name {room_name}.')
        if self.__mongo_db.get_collection(room_name) is None:
            return ChatRoom(room_name = room_name, member_list = member_list, owner_alias = owner_alias, room_type = room_type, create_new = True)
        logging.debug(f'Instance of {room_name} collection already exists.')
        return None

    def add(self, new_room: ChatRoom) -> None:
        ''' This method will add a ChatRoom instance to the list of ChatRooms
            NOTE: this method will add the list if the room name does not already exist in the list
        '''
        for current_chat_room in self.__room_list:
            if new_room.room_name == current_chat_room.room_name:
                logging.debug(f'New room with name {new_room.room_name} already exists in {self.__room_list_name}.')
                return None
        self.__room_list.append(new_room)
        logging.debug(f'Chat room {new_room.room_name} added to the room list.')
        self.__persist()

    def remove(self, room_name: str):
        ''' This method will remove a ChatRoom instance from the list of ChatRooms.
            NOTE: we want to make sure that the ChatRoom instance with the given room_name exists.
            NOTE: the use of -1 is to tell us that the ChatRoom instance was not found in the room list.
        '''
        chat_room_to_remove = self.__find_pos(room_name)
        if chat_room_to_remove is not CHAT_ROOM_INDEX_NOT_FOUND:
            self.__room_list.pop(chat_room_to_remove)
            logging.debug(f'ChatRoom {room_name} was removed from the room list.')
            self.__persist()
        else:
            logging.debug(f'ChatRoom {room_name} was not found in the room list.')

    def find_room_in_metadata(self, room_name: str) -> dict:
        ''' This method will return a dictionary of information, relating to the metadata...?
            NOTE: most likely this method will just access the metadata and find the room
            NOTE: metadata will consist of:
                    - room_name
                    - room_type
                    - owner_alias
                    - member_list
            NOTE: this is mainly for restoring a room_list
        '''
        if self.get(room_name = room_name) is None:
            logging.warning(f'No metadata can be found for {room_name}')
            return None
        else:
            room_found = self.get(room_name = room_name)
            return {
                'room_name': room_found.room_name,
                'room_type': room_found.room_type,
                'owner_alias': room_found.owner_alias,
                'member_list': room_found.member_list
            }

    def get_rooms(self):
        ''' This method will return the rooms in the room list.
            NOTE: The room list can be empty
            NOTE: this may just be the room names or not
        '''
        logging.info('Returned the list of rooms.')
        return self.__room_list

    def get(self, room_name: str) -> ChatRoom:
        ''' This method will return a ChatRoom instance, given the name of the room, room_name.
            NOTE: It is possible for a ChatRoom instance to not be in the list of rooms.
            NOTE: do we create a new ChatRoom if the chatroom was not found?
        '''
        logging.info(f'Attemping to get a chat room with name {room_name}.')
        for chat_room in self.__room_list:
            if chat_room.room_name == room_name:
                logging.debug(f'{room_name} was found in the chat room list.')
                return chat_room
        logging.debug(f'{room_name} was not found in the chat room list.')
        return None

    def __find_pos(self, room_name: str) -> int:
        ''' This method is most likely a helper method for getting the position of a ChatRoom instance is in a list.
            NOTE: This maybe just for find_by_member and find_by_owner.
            NOTE: returning -1 if the room instance cannot be found.
            NOTE: This is used for removing a chatroom instance in the list
        '''
        for chat_room_index in range(len(self.__room_list)):
            if self.__room_list[chat_room_index].room_name is room_name:
                logging.debug(f'{room_name} was found in the room list.')
                return chat_room_index
        logging.debug(f'Room name {room_name} was not found in the room list.')
        return CHAT_ROOM_INDEX_NOT_FOUND
    
    def find_by_member(self, member_alias: str) -> list:
        ''' This method will return a list of ChatRoom instances that has the the current alias within the list of
                member_aliases in the ChatRoom instance.
            NOTE: it is possible for all rooms to not have a the member_alias within their instance. return a empty list
            NOTE: create a new list and append the ChatRooms to the list.
            TODO: using the member_alias, find all rooms with a members_list that has this alias
            TODO: check if this member_alias is valid
        '''
        logging.info(f'Attempting to find chat rooms for member {member_alias} in {self.__room_list_name}.')
        if member_alias not in self.__user_list.user_aliases:
            logging.debug(f'Alias {member_alias} was not found in the list of users!')
            return []
        found_member_chat_rooms = list()
        for current_chat_room in self.__room_list:
            if member_alias in current_chat_room.member_list:
                found_member_chat_rooms.append(current_chat_room)
        logging.info(f'Returning a list of chat rooms with the member alias of {member_alias}.')
        return found_member_chat_rooms

    def find_by_owner(self, owner_alias: str) -> list:
        ''' This method will return a list of ChatRoom instances that have an owner_alias that the user is searching for.
            NOTE: it is possible for all rooms to not have the current owner_alias.
            NOTE: create a new list and append ChatRooms that have the same alias.
        '''
        logging.info(f'Attempting to find chat rooms for owner {owner_alias} in {self.__room_list_name}.')
        if owner_alias not in self.__user_alias_list.user_aliases:
            logging.debug(f'Owner alias {owner_alias} was not found in the list of users!')
            return []
        found_owner_chat_rooms = list()
        for current_chat_room in self.__room_list:
            if owner_alias is current_chat_room.owner_alias:
                found_owner_chat_rooms.append(current_chat_room)
        logging.info(f'Returning a list of chat rooms with the owner alias of {owner_alias}.')
        return found_owner_chat_rooms

    def __persist(self):
        ''' This method will save the metadata of the RoomList class and push it to the collections
            NOTE: the metadata should contain the list of room_names in the metadata where we would collect the room_names and find the room based on
        '''
        logging.info(f'Beginning the persistence process for the room list: {self.__room_list_name}')
        if self.__mongo_collection.find_one({ 'list_name': self.__room_list_name }) is None:
            logging.info(f'Persisting new room list {self.__room_list_name}.')
            self.__room_id = self.__mongo_collection.insert_one({'list_name':self.__room_list_name,                                                            
                                                                'create_time': self.__room_list_create,
                                                                'modify_time': self.__room_list_modify,
                                                                'rooms_metadata': [self.find_room_in_metadata(user_alias) for user_alias in self.__user_list.user_aliases]}) # metadata here
        else:
            if self.__dirty == True:
                logging.debug(f'Updating persistence of {self.__room_list_name} metadata.')
                self.__mongo_collection.replace_one({'list_name':self.__room_list_name,                                                   
                                                    'create_time': self.__room_list_create,
                                                    'modify_time': self.__room_list_modify,
                                                    'rooms_metadata': [self.find_room_in_metadata(user_alias) for user_alias in self.__user_list.user_aliases]},
                                                    upsert = True) # metadata here and upsert = True to update the room metadata
        self.__dirty = False

    def __restore(self) -> bool:
        ''' This method will load the metadata from the collection of the RoomList class and load it to the instance.
            NOTE: the collection will have to be checked for all ChatRoom aliases
            TODO: take in the rooms_metadata for one of the methods
            TODO: restore all of the chat rooms through the metadata in the collections.
        '''
        logging.info('Beginning the restore process.')
        room_metadata = self.__mongo_collection.find_one({ 'list_name' : self.__room_list_name })
        if room_metadata is None:
            logging.debug(f'Room name {self.__room_list_name} was not found in the collections.')
            return False
        self.__room_list_name = room_metadata['list_name']
        self.__room_list_create = room_metadata['create_time']
        self.__room_list_modify = room_metadata['modify_time']
        self.__rooms_metadata = room_metadata['rooms_metadata']
        '''room metadata is a list of dictionaries with metadata for a room'''
        for current_room_metadata in self.__rooms_metadata:
            new_chatroom = ChatRoom(room_name = current_room_metadata['room_name'],
                                    member_list = current_room_metadata['member_list'],
                                    owner_alias = current_room_metadata['owner_alias'],
                                    room_type = current_room_metadata['room_type'])
            self.__room_list.append(new_chatroom)
            logging.debug('Room', current_room_metadata['room_name'], 'has been added to the room list.')
        logging.info(f'All rooms in {self.__room_list_name} placed into the room list.')
        return True
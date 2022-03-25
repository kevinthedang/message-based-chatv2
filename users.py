import queue
import logging
from constants import *
from datetime import date, datetime
from pymongo import MongoClient
from constants import *

logging.basicConfig(filename='user.log', level=logging.DEBUG, format = LOG_FORMAT)
        
class ChatUser():
    """ class for users of the chat system. Users must be registered 
    """
    def __init__(self, alias: str, create_time: datetime = datetime.now(), modify_time: datetime = datetime.now()) -> None:
        self.__alias = alias
        self.__create_time = create_time
        self.__modify_time = modify_time

    @property
    def alias(self):
        return self.__alias
    
    @property
    def dirty(self):
        return self.__dirty

    def to_dict(self):
        return {
                'alias': self.__alias,
                'create_time': self.__create_time,
                'modify_time': self.__modify_time
        }
        
class UserList():
    """ List of users, inheriting list class
    """
    def __init__(self, list_name: str = DEFAULT_USER_LIST_NAME) -> None:
        self.__list_name = list_name
        self.__user_list = list()
        self.__user_aliases = list()
        self.__mongo_client = MongoClient('mongodb://34.94.157.136:27017/')
        self.__mongo_db = self.__mongo_client.detest
        self.__mongo_collection = self.__mongo_db.users    
        if self.__restore() is True:
            print('UserList Document is found')
            self.__dirty = False
        else:
            self.__create_time = datetime.now()
            self.__modify_time = datetime.now()
            self.__dirty = True

    @property
    def user_list(self):
        ''' This property is just to the the list of users
        '''
        return self.__user_list

    @property
    def user_aliases(self):
        ''' This property is to get the list of user_aliases
        '''
        return self.__user_aliases
    
    def register(self, new_alias: str) -> ChatUser:
        """ This method will just return a new ChatUser that will need to be added to the UserList
            This only creates the user, it does not add them to the list of users yet.
            NOTE: we check if the user already exists, if so, don't make another user with that alias
        """
        if self.get(new_alias) is not None:
            return ChatUser(alias = new_alias)
        else:
            return None

    def get(self, target_alias: str) -> ChatUser:
        ''' This method will return the user from the user_list
            TODO: Learn how to traverse through the list.
        '''
        for user_index in range(1, len(self.__user_list)):
            if target_alias == self.__user_list[user_index].alias:
                return self.__user_list[user_index].alias
        return None

    def get_all_users_aliases(self) -> list:
        ''' This method will just return the list of names as a result.
            NOTE: This list should not be empty as there should at least be an owner to the list
            TODO: Return a list of user aliases, make sure this works
        '''
        return [user.alias for user in self.__user_list]

    def append(self, new_user: ChatUser) -> None:
        ''' This method will add the user to the to the list of users
            NOTE: May want to make sure that the new_user is valid
            TODO: make sure the user does not already exist in the users (check the user_list_alias or user_list)
        '''
        if new_user in self.__user_aliases:
            logging.debug(f'Alias {new_user.alias} is an already existing user.')
            return None
        self.__user_list.append(new_user)
        self.__persist()

    def __restore(self) -> bool:
        """ First get the document for the queue itself, then get all documents that are not the queue metadata
            NOTE: we should have a list of aliases of the for the members that belong in a certain group chat.
            NOTE: we may not need the user aliases since we just want to restore all of the users
            TODO: restore the list of users to the user_list (list of user classes)
        """
        queue_metadata = self.__mongo_collection.find_one( { 'name': self.__list_name })
        if queue_metadata is None:
            return False
        self.__list_name = queue_metadata["list_name"]
        self.__create_time = queue_metadata["create_time"]
        self.__modify_time = queue_metadata["modify_time"]
        self.__user_aliases = queue_metadata['user_aliases']
        # below we want to restore the users to the userList

        return True

    def __persist(self):
        """ First save a document that describes the user list (name of list, create and modify times)
            Second, for each user in the list create and save a document for that user
            TODO: now we want to persist each user in the userlist if they are dirty = True
        """
        if self.__mongo_collection.find_one({ 'name': self.__list_name }) is None:
            self.__mongo_collection.insert_one({ "name": self.__list_name, "create_time": self.__create_time, "modify_time": self.__modify_time, 'user_names' : self.get_all_users_aliases})
        # we want to update the mongo_collection if it already exists (check if it is dirty)
        # then we want to add the users to the collection if they are dirty here
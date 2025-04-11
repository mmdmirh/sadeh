-- Create the necessary tables if they do not already exist

CREATE TABLE IF NOT EXISTS user (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(128),
    confirmed TINYINT(1) DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS conversation (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(100) DEFAULT "New Conversation",
    selected_model VARCHAR(64),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    document_mode BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS chat_message (
    id INT AUTO_INCREMENT PRIMARY KEY,
    conversation_id INT NOT NULL,
    sender VARCHAR(10),
    content TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversation(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS document (
    id INT AUTO_INCREMENT PRIMARY KEY,
    conversation_id INT NOT NULL,
    filename VARCHAR(256),
    data LONGBLOB,
    mime_type VARCHAR(128),
    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversation(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Seed the dummy user only if not already present.
INSERT INTO user (username, email, password_hash, confirmed, created_at)
SELECT 'sm.mirhoseininejad', 'sm.mirhoseininejad@gmail.com', 
       'pbkdf2:sha256:600000$abcdef123456$3fc7fbd764859cf76156a3ec7b646d21b2f1fcfa8d36a72a99a5fa400b8ed3d2', 
       1, NOW()
FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM user WHERE email = 'sm.mirhoseininejad@gmail.com'
);

-- Insert initial test data: create a conversation for the dummy user if not exists.
INSERT INTO conversation (user_id, selected_model, created_at, document_mode)
SELECT u.id, 'default', NOW(), FALSE
FROM user u
WHERE u.email = 'sm.mirhoseininejad@gmail.com'
  AND NOT EXISTS (
        SELECT 1 FROM conversation c WHERE c.user_id = u.id
  );

-- Update the title for the conversation we just created (if title column exists)
-- Using a derived table to avoid the MySQL error 1093
UPDATE conversation c
JOIN user u ON c.user_id = u.id
JOIN (
    SELECT user_id, MAX(created_at) as max_created_at
    FROM conversation
    GROUP BY user_id
) latest ON c.user_id = latest.user_id AND c.created_at = latest.max_created_at
SET c.title = 'Welcome Conversation'
WHERE u.email = 'sm.mirhoseininejad@gmail.com';

-- Insert an initial welcome message for the above conversation if not exists.
INSERT INTO chat_message (conversation_id, sender, content, created_at)
SELECT c.id, 'ai', 'Welcome to the chat! How can I assist you today?', NOW()
FROM conversation c
JOIN user u ON c.user_id = u.id
WHERE u.email = 'sm.mirhoseininejad@gmail.com'
  AND NOT EXISTS (
        SELECT 1 FROM chat_message m WHERE m.conversation_id = c.id
  )
ORDER BY c.created_at DESC
LIMIT 1;

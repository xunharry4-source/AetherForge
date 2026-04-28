import logging
import sys
import os
import warnings

# 屏蔽三方库的基础导入与兼容性警告，确保输出只关注核心业务逻辑
warnings.filterwarnings("ignore", message=".*missing imports.*")
warnings.filterwarnings("ignore", category=SyntaxWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

def get_logger(name="novel_agent"):
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Console handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        
        # File handler (Optional, for true persistence)
        try:
            from .config_utils import load_config
            config = load_config()
            log_base = config.get("LOG_PATH", "logs")
            
            if not os.path.isabs(log_base):
                # Project root is parent of src/
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                log_dir = os.path.join(project_root, log_base)
            else:
                log_dir = log_base
                
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, 'novel_agent.log')
            fh = logging.FileHandler(log_file)
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        except Exception:
            pass
            
    return logger

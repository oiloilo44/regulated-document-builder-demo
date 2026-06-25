"""db_updater.py 핵심 로직 단위 테스트"""

import os
import pytest

from test_record_builder.db_updater import DBUpdater
from test_record_builder.config import DBConnectionConfig
from test_record_builder.exceptions import PDFProcessingError


class TestBuildConnectionString:
    """_build_connection_string 메서드 테스트"""

    def test_trusted_connection(self):
        cfg = DBConnectionConfig(
            server="localhost",
            port=1433,
            database="TestDB",
            driver="{ODBC Driver 17 for SQL Server}",
            trusted_connection=True,
        )
        updater = DBUpdater(cfg)
        conn_str = updater._build_connection_string()
        
        assert "DRIVER={ODBC Driver 17 for SQL Server}" in conn_str
        assert "SERVER=localhost,1433" in conn_str
        assert "DATABASE=TestDB" in conn_str
        assert "Trusted_Connection=yes" in conn_str

    def test_user_password_connection(self):
        cfg = DBConnectionConfig(
            server="203.0.113.10",
            port=1433,
            database="ProdDB",
            user="testuser",
            password="testpass",
            driver="{ODBC Driver 17 for SQL Server}",
            trusted_connection=False,
        )
        updater = DBUpdater(cfg)
        conn_str = updater._build_connection_string()
        
        assert "UID=testuser" in conn_str
        assert "PWD=testpass" in conn_str
        assert "Trusted_Connection" not in conn_str

    def test_missing_credentials_raises(self):
        cfg = DBConnectionConfig(
            server="localhost",
            port=1433,
            database="TestDB",
            user="",
            password="",
            driver="{ODBC Driver 17 for SQL Server}",
            trusted_connection=False,
        )
        updater = DBUpdater(cfg)
        
        with pytest.raises(PDFProcessingError, match="인증 정보가 누락"):
            updater._build_connection_string()


class TestBuildUpdateStatement:
    """_build_update_statement 메서드 테스트"""

    def test_builds_query(self):
        cfg = DBConnectionConfig()
        updater = DBUpdater(cfg)
        
        query, params = updater._build_update_statement(
            prt_req_no="REQ001",
            prt_req_seq="1",
            output_filename="output.pdf",
            output_dir_path="D:/output",
        )
        
        assert "UPDATE ERPBiz.dbo.PPTestRecordDetail" in query
        assert "WHERE PrtReqNo = ? AND PrtReqSeq = ?" in query
        assert params[0] == "output.pdf"
        assert params[1] == "D:/output"
        assert params[2] == "REQ001"
        assert params[3] == "1"

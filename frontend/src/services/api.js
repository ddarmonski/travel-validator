// api.js
import axios from 'axios'

const apiClient = axios.create({
  baseURL: process.env.NODE_ENV === 'production' ? '/api' : '/api',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000
})

const validateFiles = (files) => {
  if (!files || files.length === 0) {
    throw new Error('No files provided');
  }
  
  if (files.length > 5) {
    throw new Error('Maximum 5 files allowed');
  }

  for (const file of files) {
    if (file.size > 10 * 1024 * 1024) {
      throw new Error(`File ${file.name} exceeds 10MB limit`);
    }
    if (!file.type.toLowerCase().includes('pdf')) {
      throw new Error(`File ${file.name} is not a PDF`);
    }
  }
}

export default {
  async generateReport(files) {
    try {
      validateFiles(files);

      const formData = new FormData();
      files.forEach((file) => {
        formData.append('files', file);
      });

      const response = await apiClient.post('/travel-requests/generate-report/', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        },
        timeout: 300000 // 5 minutes for large files
      });

      return response;
    } catch (error) {
      const errorMessage = error.response?.data?.error || error.message || 'Error generating report';
      throw new Error(errorMessage);
    }
  },

  async submitReport(reportData) {
    try {
      const formData = new FormData();
      
      // Add report metadata as JSON string
      const metadata = {
        requester: reportData.requester,
        department: reportData.department,
        position: reportData.position,
        start_date: reportData.start_date,
        end_date: reportData.end_date,
        total_amount: reportData.total_amount,
        expenses: reportData.expenses
      };
      
      formData.append('data', JSON.stringify(metadata));
      
      // Add files if present
      if (reportData.files && reportData.files.length) {
        validateFiles(reportData.files);
        reportData.files.forEach(file => {
          formData.append('files', file);
        });
      }

      const response = await apiClient.post('/travel-requests/submit-report/', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        },
        timeout: 300000 // 5 minutes for large files
      });
      
      return response;
    } catch (error) {
      const errorMessage = error.response?.data?.error || error.message || 'Error submitting report';
      throw new Error(errorMessage);
    }
  },

  async updateReport(reportId, reportData) {
    try {
      const response = await apiClient.put(
        `/travel-requests/${reportId}/update-report/`, 
        reportData
      );
      return response;
    } catch (error) {
      const errorMessage = error.response?.data?.error || error.message || 'Error updating report';
      throw new Error(errorMessage);
    }
  }
}
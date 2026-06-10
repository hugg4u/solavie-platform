import { maskPhoneNumberString, maskObject } from './structured-logger.service';

describe('StructuredLogger PII Masking', () => {
  describe('maskPhoneNumberString', () => {
    it('should mask standard Vietnamese phone numbers', () => {
      expect(maskPhoneNumberString('0987654321')).toBe('098****321');
      expect(maskPhoneNumberString('+84987654321')).toBe('+84******321');
    });

    it('should mask phone numbers embedded in a text message', () => {
      const msg = 'User registered with phone 0987654321 and secondary phone 0123456789';
      const expected = 'User registered with phone 098****321 and secondary phone 012****789';
      expect(maskPhoneNumberString(msg)).toBe(expected);
    });

    it('should not mask random numbers that are not phone numbers', () => {
      expect(maskPhoneNumberString('12345')).toBe('12345');
      expect(maskPhoneNumberString('1234567890123456')).toBe('1234567890123456');
    });
  });

  describe('maskObject', () => {
    it('should recursively mask object fields matching phone patterns', () => {
      const input = {
        name: 'Nguyen Van A',
        phone: '0987654321',
        nested: {
          phone_number: '+84987654321',
          normalField: 'hello 123456',
        },
        array: ['0123456789', { phoneNumber: '0981112222' }],
      };

      const expected = {
        name: 'Nguyen Van A',
        phone: '098****321',
        nested: {
          phone_number: '+84******321',
          normalField: 'hello 123456',
        },
        array: ['012****789', { phoneNumber: '098****222' }],
      };

      expect(maskObject(input)).toEqual(expected);
    });
  });
});

import { IsEmail, IsString, IsOptional } from 'class-validator';

export class InviteUserDto {
  @IsEmail({}, { message: 'Địa chỉ email không hợp lệ' })
  email!: string;

  @IsString()
  @IsOptional()
  firstName?: string;

  @IsString()
  @IsOptional()
  lastName?: string;

  @IsString()
  @IsOptional()
  department?: string;
}

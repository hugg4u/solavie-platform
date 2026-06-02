import { IsString, IsOptional, IsBoolean } from 'class-validator';

export class UpdatePreferencesDto {
  @IsString()
  @IsOptional()
  theme?: string;

  @IsString()
  @IsOptional()
  language?: string;

  @IsBoolean()
  @IsOptional()
  notificationsEnabled?: boolean;
}
